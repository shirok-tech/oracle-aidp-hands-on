"""Original census Excel adapters. Used verbatim inside nb01; no Spark needed here."""
from pathlib import Path
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
import openpyxl
from openpyxl.utils.cell import column_index_from_string, coordinate_to_tuple

TOKYO_CODES = set(
    [str(x) for x in range(13101, 13124)]
    + [str(x) for x in range(13201, 13216)]
    + [str(x) for x in range(13218, 13226)]
    + ['13227', '13228', '13229', '13303', '13305', '13307', '13308',
       '13361', '13362', '13363', '13364', '13381', '13382', '13401', '13402', '13421']
)
assert len(TOKYO_CODES) == 62


def count_value(value, field, nullable_dash=False):
    """Keep '-' only for age_unknown; never silently coerce unexpected symbols."""
    if nullable_dash and value == '-':
        return None
    if value is None or isinstance(value, bool):
        raise ValueError(f'{field}: empty/non-count value {value!r}')
    try:
        number = Decimal(str(value).replace(',', '').strip())
    except InvalidOperation as exc:
        raise ValueError(f'{field}: unexpected count symbol {value!r}') from exc
    if not number.is_finite() or number != number.to_integral_value() or number < 0:
        raise ValueError(f'{field}: invalid nonnegative integer {value!r}')
    return int(number)


def decimal_value(value, field):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field}: unexpected percentage {value!r}') from exc
    if not math.isfinite(number):
        raise ValueError(f'{field}: non-finite percentage')
    return number


def clean_name(value):
    value = str(value)
    if '_' not in value:
        raise ValueError(f'Area-name code prefix missing: {value!r}')
    return value.split('_', 1)[1]


def canonical_hash(records):
    """Fingerprint canonical curated values; identical to comparison_core.canonical_hash."""
    return hashlib.sha256(json.dumps(sorted(records, key=lambda r: r['area_code']),
        ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def extract_year(raw_year_dir, config):
    """Return (62 canonical records, verification details) using year-specific anchors."""
    population, families, ages, source_files, aggregate = {}, {}, {}, {}, {}
    for kind, definition in config['sources'].items():
        source_path = Path(raw_year_dir) / definition['filename']
        if not source_path.is_file():
            raise FileNotFoundError(f'Upload the official original workbook: {source_path}')
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        workbook = openpyxl.load_workbook(source_path, read_only=True, data_only=True)
        try:
            if definition['sheet'] not in workbook.sheetnames:
                raise ValueError(f'{kind}: expected sheet {definition["sheet"]!r} not found')
            sheet = workbook[definition['sheet']]
            header = list(sheet.iter_rows(max_row=definition['first_data_row']-1, values_only=True))
            for address, expected in definition['header_anchors'].items():
                rr, cc = coordinate_to_tuple(address)
                actual = header[rr-1][cc-1]
                if actual != expected:
                    raise ValueError(f'{kind} {address}: expected {expected!r}; actual {actual!r}')
            # Check the actual headings before the file fingerprint so structural drift is explicit.
            if digest != definition['verified_file_sha256']:
                raise ValueError(f'{kind}: SHA-256 differs from the inspected source. Check official '
                                 'revision information, re-inspect totals, then revise the registry.')
            columns = {key: column_index_from_string(letter)-1
                       for key, letter in definition['columns'].items()}
            source_files[kind] = {'path': str(source_path), 'sha256': digest,
                                 'stat_infid': definition['stat_infid'],
                                 'page_url': definition['page_url'], 'header_check': 'PASS'}
            for source_row, values in enumerate(sheet.iter_rows(
                    min_row=definition['first_data_row'], values_only=True),
                    definition['first_data_row']):
                def value(field):
                    return values[columns[field]]
                if value('prefecture') != '13_東京都':
                    continue
                if kind == 'households':
                    code = str(value('area_name_code')).split('_', 1)[0]
                else:
                    code = str(value('area_code'))
                is_total = code == '13000' and value('region_type') == 'a'
                is_municipality = code in TOKYO_CODES and str(value('region_type')) in {'0', '2', '3'}
                if not (is_total or is_municipality):
                    continue  # Tokyo/ward aggregate and historical boundary rows are excluded.
                if kind == 'population':
                    if code in population:
                        raise ValueError(f'population duplicate code: {code}')
                    population[code] = {'area_code': code, 'area_name': clean_name(value('area_name')),
                        'population': count_value(value('population'), 'population'),
                        'general_households': count_value(value('general_households'), 'general_households'),
                        'households': count_value(value('households'), 'households'),
                        'population_previous_rearranged': count_value(value('population_previous_rearranged'), 'population_previous_rearranged'),
                        'population_change_pct_source': decimal_value(value('population_change_pct_source'), 'population_change_pct_source'),
                        'population_source_row': source_row}
                elif kind == 'households':
                    family_type = value('family_type')
                    if family_type not in {'0_総数', '3_単独世帯'}:
                        continue
                    family_key = 'general_households' if family_type == '0_総数' else 'single_households'
                    entry = families.setdefault(code, {'area_name': clean_name(value('area_name_code'))})
                    if family_key in entry:
                        raise ValueError(f'households duplicate: {code}/{family_type}')
                    entry[family_key] = count_value(value('general_households'), family_key)
                    entry[family_key+'_source_row'] = source_row
                elif kind == 'age':
                    if value('nationality') != '0_国籍総数' or value('sex') != '0_総数':
                        continue
                    if code in ages:
                        raise ValueError(f'age duplicate code: {code}')
                    ages[code] = {'area_name': clean_name(value('area_name')),
                        **{field: count_value(value(field), field, nullable_dash=field=='age_unknown')
                           for field in ['age_total', 'age_under15', 'age_15_64', 'age_65plus', 'age_unknown']},
                        'age_unknown_raw': str(value('age_unknown')),
                        'age_65plus_share_known_source_pct': decimal_value(value('age_65plus_share_known_source_pct'), 'age_65plus_share_known_source_pct'),
                        'age_source_row': source_row}
        finally:
            workbook.close()

    expected_keys = TOKYO_CODES | {'13000'}
    for name, rows in [('population', population), ('households', families), ('age', ages)]:
        if set(rows) != expected_keys:
            raise ValueError(f'{name}: unexpected area set; missing={sorted(expected_keys-set(rows))}; '
                             f'extra={sorted(set(rows)-expected_keys)}')
    output = []
    for code in sorted(expected_keys):
        p, h, a = population[code], families[code], ages[code]
        if not p['area_name'] == h['area_name'] == a['area_name']:
            raise ValueError(f'{code}: area names differ between tables')
        if h.get('general_households') != p['general_households'] or 'single_households' not in h:
            raise ValueError(f'{code}: general households differ between tables / single-household row missing')
        if a['age_total'] != p['population']:
            raise ValueError(f'{code}: age total and population differ')
        known = sum(a[f] for f in ['age_under15', 'age_15_64', 'age_65plus'])
        if min(p['population'], p['population_previous_rearranged'], p['general_households'], known) <= 0:
            raise ValueError(f'{code}: nonpositive denominator')
        if not 0 <= h['single_households'] <= p['general_households'] <= p['households']:
            raise ValueError(f'{code}: invalid household counts')
        if known > p['population']:
            raise ValueError(f'{code}: known-age population exceeds total population')
        if a['age_unknown'] is not None and known+a['age_unknown'] != p['population']:
            raise ValueError(f'{code}: age groups do not sum to total')
        if abs(a['age_65plus']/known*100-a['age_65plus_share_known_source_pct']) > 0.000011:
            raise ValueError(f'{code}: recalculated elderly share disagrees with source')
        if abs((p['population']/p['population_previous_rearranged']-1)*100-p['population_change_pct_source']) > 0.000011:
            raise ValueError(f'{code}: recalculated population growth disagrees with source')
        record = {**p, **{f: a[f] for f in ['age_under15', 'age_15_64', 'age_65plus', 'age_unknown',
                                          'age_unknown_raw', 'age_65plus_share_known_source_pct', 'age_source_row']},
                  'single_households': h['single_households'],
                  'single_source_row': h['single_households_source_row'],
                  'census_year': config['census_year'], 'reference_date': config['reference_date'],
                  'population_previous_year': config['population_previous_year'], 'series': 'original',
                  'boundary_basis': config['boundary_basis'], 'unknown_policy': config['unknown_policy']}
        if code == '13000':
            aggregate = record
        else:
            output.append(record)
    # Exact additive checks against the Tokyo aggregate, independent of the 62 row filter.
    fields = ['population', 'general_households', 'households', 'single_households',
              'age_under15', 'age_15_64', 'age_65plus', 'population_previous_rearranged']
    totals = {field: sum(row[field] for row in output) for field in fields}
    for field in fields:
        if totals[field] != aggregate[field]:
            raise ValueError(f'Tokyo aggregate mismatch for {field}: {totals[field]} != {aggregate[field]}')
    unknown_null_codes = [row['area_code'] for row in output if row['age_unknown'] is None]
    verification = {'status': 'PASS', 'census_year': config['census_year'], 'rows': len(output),
        'reference_date': config['reference_date'], 'series': 'original',
        'boundary_basis': config['boundary_basis'], 'unknown_policy': config['unknown_policy'],
        'totals': totals, 'tokyo_aggregate': aggregate,
        'curated_sha256': canonical_hash(output),
        'age_unknown_nulls': len(unknown_null_codes), 'age_unknown_null_codes': unknown_null_codes,
        'source_files': source_files,
        'note': 'Original dash symbols remain NULL. Unknown-rate deltas remain NULL if either year is NULL.'}
    return output, verification
