# Mass reading fixtures

Public AJAX responses from https://ktcgkpv.org/readings/mass-reading,
retrieved on 2026-10-04 with explicit day/month/year/seldate parameters.
Only unused audio_list fields have been removed. Tests use these files offline.

- weekday.json: 2026-10-03, no second reading; multiple communion antiphons.
- sunday-multiple-masses.json: 2026-10-04, transferred Rosary celebration first,
  followed by the ordinary Sunday readings. Source order is intentional.
- multiple-readings.json: 2026-10-07, multiple choices for the first reading.
- long-short-gospel.json: 2026-10-11, long Gospel first, short Gospel second.

The response data.today is the server's current date, even for another requested
reading date. It must not be used as the selected reading date.

special.json is a small synthetic fixture for the public source JavaScript's
is_special/special_content branch: only the first direct .selectable child of
each .division is displayed. Historical Holy Week AJAX requests were refused
for anonymous access, so this fixture is a DOM-contract test, not a captured
Holy Week response.
