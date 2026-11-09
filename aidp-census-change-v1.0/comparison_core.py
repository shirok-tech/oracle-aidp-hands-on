"""Small-data validation and a local reference calculation; Spark computes production metrics."""
import hashlib
import json
import math

TOKYO_CODES = {str(x) for x in range(13101, 13124)} | {
    str(x) for x in [13201,13202,13203,13204,13205,13206,13207,13208,13209,
    13210,13211,13212,13213,13214,13215,13218,13219,13220,13221,13222,
    13223,13224,13225,13227,13228,13229,13303,13305,13307,13308,13361,
    13362,13363,13364,13381,13382,13401,13402,13421]}
BOUNDARY_REASON = {
    'area_code': '13209', 'area_name': '町田市',
    'reason': '2020-12-01境界変更。人口だけを組み替えても世帯・年齢の比較条件は揃わないため除外。',
    'effective_date': '2020-12-01',
    'source_url': 'https://www.city.sagamihara.kanagawa.jp/shisei/1026766/seido/1026777/1004437.html',
    'supporting_url': 'https://www.gikai-machida.jp/voices/GikaiDoc/attach/Gk/Gk5001_64_somu_gyosei_kyokaihenko.pdf'
}
COUNT_FIELDS = ['population','general_households','single_households',
                'age_under15','age_15_64','age_65plus']

def validate_year_records(records, year):
    if len(records) != 62 or {r['area_code'] for r in records} != TOKYO_CODES:
        raise ValueError(f'{year}: current Tokyo municipality coverage must be exactly 62 unique codes')
    for r in records:
        if r['census_year'] != year or r['series'] != 'original' or r['reference_date'] != f'{year}-10-01':
            raise ValueError(f'{year}: wrong year, reference date or series')
        for key in COUNT_FIELDS:
            if type(r[key]) is not int or r[key] < 0:
                raise ValueError(f"{r['area_code']}: invalid integer count {key}")
        known = sum(r[k] for k in ['age_under15','age_15_64','age_65plus'])
        if r['population'] <= 0 or r['general_households'] <= 0 or known <= 0:
            raise ValueError('Zero denominator')
        if r['single_households'] > r['general_households'] or known > r['population']:
            raise ValueError('Inconsistent population/household counts')
        unknown = r['age_unknown']
        if unknown is not None and (type(unknown) is not int or unknown < 0 or known + unknown != r['population']):
            raise ValueError('Age totals disagree with population')
        if year == 2025 and (type(r['population_previous_rearranged']) is not int or r.get('population_previous_year') != 2020):
            raise ValueError('2025 must contain a complete rearranged 2020 population')
    return {r['area_code']: r for r in records}

def compare_scope(old_records, new_records, boundary_policy):
    old = validate_year_records(old_records, 2020)
    new = validate_year_records(new_records, 2025)
    diffs = [{'area_code': c, 'area_name': new[c]['area_name'],
              'population_2020_original': old[c]['population'],
              'population_2020_rearranged': new[c]['population_previous_rearranged'],
              'difference': new[c]['population_previous_rearranged'] - old[c]['population']}
             for c in sorted(TOKYO_CODES)
             if new[c]['population_previous_rearranged'] != old[c]['population']]
    if boundary_policy == 'strict':
        excluded = []
        accepted = not diffs
    elif boundary_policy == 'exclude_documented_machida':
        # Deliberate scope choice backed by the cited boundary record, not a tolerance.
        excluded = ['13209']
        accepted = all(d['area_code'] == '13209' and d['difference'] == 4 for d in diffs)
    else:
        raise ValueError('Unsupported boundary_policy')
    return {'accepted': accepted, 'differences': diffs,
            'input_municipality_count': 62, 'rows': 62 - len(excluded),
            'excluded_area_codes': excluded,
            'excluded_reasons': [BOUNDARY_REASON] if excluded else [],
            'boundary_policy': boundary_policy,
            'caveat': 'Population agreement is a check, not proof that every demographic definition is unchanged.'}

def reference_changes(old_records, new_records, scope):
    if not scope['accepted']:
        raise ValueError('Unresolved boundary mismatch; no ML input may be generated')
    old = {r['area_code']: r for r in old_records}
    new = {r['area_code']: r for r in new_records}
    output = []
    for c in sorted(TOKYO_CODES - set(scope['excluded_area_codes'])):
        row = {'area_code': c, 'area_name': new[c]['area_name']}
        for year, source in [(2020, old[c]), (2025, new[c])]:
            known = source['age_under15'] + source['age_15_64'] + source['age_65plus']
            row[f'population_{year}'] = source['population']
            row[f'single_households_pct_{year}'] = source['single_households'] / source['general_households'] * 100.0
            row[f'age_65plus_share_known_pct_{year}'] = source['age_65plus'] / known * 100.0
            row[f'age_unknown_pct_{year}'] = None if source['age_unknown'] is None else source['age_unknown'] / source['population'] * 100.0
        row['population_growth_pct'] = (row['population_2025'] / row['population_2020'] - 1.0) * 100.0
        row['single_share_change_pp'] = row['single_households_pct_2025'] - row['single_households_pct_2020']
        row['elderly_share_change_pp'] = row['age_65plus_share_known_pct_2025'] - row['age_65plus_share_known_pct_2020']
        row['age_unknown_change_pp'] = (None if row['age_unknown_pct_2020'] is None or row['age_unknown_pct_2025'] is None
                                       else row['age_unknown_pct_2025'] - row['age_unknown_pct_2020'])
        output.append(row)
    return output

def canonical_hash(records):
    return hashlib.sha256(json.dumps(sorted(records, key=lambda r: r['area_code']),
        ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()
