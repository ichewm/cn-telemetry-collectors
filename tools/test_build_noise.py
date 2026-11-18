import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_noise import COUNT, RECORD, encode_corpus


class NoiseCorpusTests(unittest.TestCase):
    def test_roundtrip_fixed_width(self):
        domains = ['example.com', 'a.co', 'x.' + 'y' * 20 + '.org'][:2] + ['b.net']
        blob, n = encode_corpus(['example.com', 'b.net', 'a.co'])
        self.assertEqual(len(blob) % RECORD, 0)
        recs = [blob[i * RECORD:blob.find(b'\x00', i * RECORD)].decode()
                for i in range(n)]
        self.assertEqual(recs, ['example.com', 'b.net', 'a.co'])  # rank order kept
        self.assertEqual(blob[:RECORD], b'example.com' + b'\x00' * (RECORD - 11))

    def test_www_stripped_and_invalid_skipped(self):
        blob, n = encode_corpus(['www.news.com', 'NOT A DOMAIN', 'ok.io'])
        recs = [blob[i * RECORD:blob.find(b'\x00', i * RECORD)].decode()
                for i in range(n)]
        self.assertEqual(recs, ['news.com', 'ok.io'])

    def test_overlength_and_dupes_skipped(self):
        longd = 'z' * 40 + '.com'
        blob, n = encode_corpus([longd, 'dup.com', 'dup.com', 'fine.tv'])
        recs = [blob[i * RECORD:blob.find(b'\x00', i * RECORD)].decode()
                for i in range(n)]
        self.assertEqual(recs, ['dup.com', 'fine.tv'])

    def test_seek_addressing(self):
        # the property the firmware depends on: record i lives at i*32
        blob, n = encode_corpus([f'd{i}.example.com' for i in range(50)])
        self.assertEqual(n, 50)
        idx = 37
        rec = blob[idx * RECORD:idx * RECORD + RECORD]
        self.assertTrue(rec.startswith(b'd37.example.com\x00'))
        self.assertEqual(len(blob), min(n, COUNT) * RECORD)


if __name__ == '__main__':
    unittest.main()
