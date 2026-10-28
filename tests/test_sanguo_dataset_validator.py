import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location(
    "validate_sanguo", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "validate_sanguo_dataset.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

C = [{"id": "a", "x": 1, "y": 2, "neighbors": ["b"]}, {"id": "b", "x": 2, "y": 2, "neighbors": ["a"]}]
O = [{"id": "zhou_yu", "name": "周瑜", "home_city": "a",
      "stats_estimate": {"leadership": 90, "war": 70, "intellect": 90, "politics": 80}}]


class ValidatorTests(unittest.TestCase):
    def test_clean_data_passes(self):
        self.assertEqual(mod.validate(C, O), [])

    def test_asymmetric_adjacency_and_unknown_city(self):
        bad = [dict(C[0]), {"id": "b", "x": 2, "y": 2, "neighbors": []}]
        self.assertTrue(any("not symmetric" in e for e in mod.validate(bad, O)))
        o = [dict(O[0], home_city="zzz")]
        self.assertTrue(any("home_city" in e for e in mod.validate(C, o)))

    def test_duplicate_and_bad_stats(self):
        dup = O + [dict(O[0])]
        self.assertTrue(any("duplicate officer" in e for e in mod.validate(C, dup)))
        bad = [dict(O[0], stats_estimate={"leadership": 101, "war": "x", "intellect": 5, "politics": 5})]
        self.assertEqual(len([e for e in mod.validate(C, bad) if "stats_estimate" in e]), 2)


if __name__ == "__main__":
    unittest.main()
