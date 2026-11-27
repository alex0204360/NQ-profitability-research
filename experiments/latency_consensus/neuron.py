"""Session-batched kernel memories for two executable return labels."""
import numpy as np


class Consensus:
    def __init__(self):
        self.sessions = []

    def observe_session(self, features, paired_returns_in_ranges):
        if len(features):
            features = np.asarray(features, dtype=float)
            labels = np.asarray(paired_returns_in_ranges, dtype=float)
            moments = np.stack([features.mean(axis=0),
                                (features*labels[:, :1]).mean(axis=0),
                                (features*labels[:, 1:2]).mean(axis=0)])
            self.sessions.append(moments)

    def project(self, u, scale, dimension):
        if not self.sessions:
            return 0., 0., 0.
        votes = np.asarray(self.sessions)[:, :, :dimension] @ u[:dimension]
        total = votes.sum(axis=0)
        retained = np.vstack([total, total - votes])
        projections = scale * retained[:,1:] / (4.0 + retained[:,:1])
        return float(projections.min()),float(projections.max()),float(projections[0].mean())
