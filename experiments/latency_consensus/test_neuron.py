import unittest

import numpy as np

from experiments.latency_consensus.neuron import Consensus


class ConsensusTests(unittest.TestCase):
    def test_project_matches_explicit_kernel_and_day_deletion(self):
        feature_days = [
            np.array([[1.0, 0.0], [0.0, 1.0]]),
            np.array([[1.0, 1.0]]),
            np.array([[0.5, -0.5], [1.5, 0.5]]),
        ]
        return_days = [
            np.array([[1.0, -1.0], [3.0, 1.0]]),
            np.array([[-2.0, 4.0]]),
            np.array([[0.5, 2.0], [-1.5, 0.0]]),
        ]
        memory = Consensus()
        for features, labels in zip(feature_days, return_days, strict=True):
            memory.observe_session(features, labels)

        query = np.array([1.0, 0.5])
        scale = 2.0
        projections = []
        for omitted in (None, 0, 1, 2):
            selected = [i for i in range(len(feature_days)) if i != omitted]
            a = np.zeros(2)
            b = np.zeros((2, 2))
            for i in selected:
                x, y = feature_days[i], return_days[i]
                a += (x.mean(axis=0) @ query)
                b[0] += ((x * y[:, :1]).mean(axis=0) @ query)
                b[1] += ((x * y[:, 1:2]).mean(axis=0) @ query)
            projections.append(scale * b / (4.0 + a))
        projections = np.asarray(projections)
        expected = (projections.min(), projections.max(), projections[0].mean())
        actual = memory.project(query, scale, dimension=2)
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-14)

    def test_warm_start_uses_four_zero_pseudo_days_and_empty_sessions_are_ignored(self):
        memory = Consensus()
        self.assertEqual(memory.project(np.array([1.0]), 3.0, dimension=1), (0.0, 0.0, 0.0))
        memory.observe_session(np.empty((0, 1)), np.empty((0, 2)))
        self.assertEqual(memory.sessions, [])
        memory.observe_session(np.array([[1.0]]), np.array([[2.0, -1.0]]))
        # All-days projection: 3 * [2, -1] / (4 + 1). Leave-one-day is zero.
        self.assertEqual(memory.project(np.array([1.0]), 3.0, dimension=1),
                         (-0.6, 1.2, 0.3))

    def test_observe_and_project_do_not_mutate_caller_arrays_or_saved_state(self):
        memory = Consensus()
        features = np.array([[1.0, 2.0], [3.0, 4.0]])
        labels = np.array([[2.0, -1.0], [4.0, 3.0]])
        features_before, labels_before = features.copy(), labels.copy()
        memory.observe_session(features, labels)
        saved = np.asarray(memory.sessions).copy()
        query = np.array([0.25, 0.75])
        query_before = query.copy()
        memory.project(query, 5.0, dimension=2)
        np.testing.assert_array_equal(features, features_before)
        np.testing.assert_array_equal(labels, labels_before)
        np.testing.assert_array_equal(query, query_before)
        np.testing.assert_array_equal(np.asarray(memory.sessions), saved)

        # Mutating the original caller-owned inputs after observation must not
        # rewrite the day moments already retained by the memory.
        features[:] = -99.0
        labels[:] = 99.0
        np.testing.assert_array_equal(np.asarray(memory.sessions), saved)


if __name__ == "__main__":
    unittest.main()
