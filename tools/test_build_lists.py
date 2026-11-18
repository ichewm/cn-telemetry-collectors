import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_lists import HASH_BYTES, fnv40, parse_list


def run_build(tmpdir, list_text):
    src = tmpdir / 'telemetry.domains'
    out = tmpdir / 'dist'
    src.write_text(list_text)
    subprocess.run([sys.executable, str(Path(__file__).with_name('build_lists.py')),
                    '--src', str(src), '--out', str(out)],
                   check=True, capture_output=True, text=True)
    return out


class FnvTests(unittest.TestCase):
    def test_matches_firmware_vectors(self):
        # Pinned against the firmware repo's tools/build_blocklist.py — these
        # vectors guarantee telemetry.bin stays loadable by the ESP32 firmware.
        self.assertEqual(fnv40('ads.example.com'), 0x58979aa55e)
        self.assertEqual(fnv40('alog.umeng.com'), 0x658dbeb375)
        self.assertEqual(fnv40('www.google-analytics.com'), 0x5ccd3caedb)

    def test_40_bit_truncation(self):
        self.assertLess(fnv40('a.very.long.domain.name.example.com'), 1 << 40)


class BuildTests(unittest.TestCase):
    LIST = ('# comment\n'
            'b.example.com | src1,src2 | probe:x | 2026-01-01\n'
            'a.example.com | src1,src2 | probe:y | 2026-01-01\n')

    def test_bin_is_sorted_little_endian_5b(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = run_build(Path(d), self.LIST)
            data = (out / 'telemetry.bin').read_bytes()
            hashes = [int.from_bytes(data[i:i + HASH_BYTES], 'little')
                      for i in range(0, len(data), HASH_BYTES)]
            self.assertEqual(hashes, sorted(hashes))
            self.assertEqual(hashes,
                             sorted(fnv40(x.split('|')[0].strip())
                                    for x in self.LIST.splitlines()
                                    if not x.startswith('#')))

    def test_hosts_and_adguard_outputs_sorted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = run_build(Path(d), self.LIST)
            hosts = (out / 'telemetry.hosts').read_text().splitlines()
            rules = (out / 'adguard.txt').read_text().splitlines()
            self.assertIn('0.0.0.0 a.example.com', hosts)
            self.assertIn('||a.example.com^', rules)
            self.assertLess(hosts.index('0.0.0.0 a.example.com'),
                            hosts.index('0.0.0.0 b.example.com'))

    def test_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 't.domains'
            src.write_text('a.com | s | e | 2026-01-01\na.com | s | e | 2026-01-01\n')
            with self.assertRaises(SystemExit):
                parse_list(src)

    def test_bad_hostname_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 't.domains'
            src.write_text('not a hostname | s | e | 2026-01-01\n')
            with self.assertRaises(SystemExit):
                parse_list(src)

    def test_real_list_parses(self):
        root = Path(__file__).parent.parent
        entries = parse_list(root / 'telemetry.domains')
        self.assertGreaterEqual(len(entries), 15)
        quarantine = parse_list(root / 'QUARANTINE.domains')
        stable = {d for d, *_ in entries}
        self.assertFalse(stable & {d for d, *_ in quarantine},
                         'a domain must not be STABLE and QUARANTINE at once')


if __name__ == '__main__':
    unittest.main()
