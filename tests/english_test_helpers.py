"""Read encrypted output only in tests to verify content and session behavior."""
import json
import subprocess
from scripts import fetch


def encrypted_shell_ciphertext(path):
    source = path.read_text(encoding="utf-8")
    encoded = source.split("var CIPHERTEXT = ", 1)[1].lstrip()
    payload, _ = json.JSONDecoder().raw_decode(encoded)
    return payload


def decrypt_english_pages(pages, passcode):
    result = subprocess.run(
        ["node", "-e", '''
const sjcl = require('./vendor/sjcl.js');
const request = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const details = {};
const output = {};
request.pages.forEach((page, index) => {
  output[page.id] = sjcl.json.decrypt(
    index === 0 ? request.passcode : details.key, page.ciphertext, {}, details
  );
});
process.stdout.write(JSON.stringify(output));
'''],
        input=json.dumps({"pages": pages, "passcode": passcode}),
        encoding="utf-8", capture_output=True, check=True, cwd=fetch.ROOT,
    )
    return json.loads(result.stdout)
