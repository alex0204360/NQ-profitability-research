"""Estimate the signed value of holding by weighting two strictly matured branches."""
class BranchValue:
    def __init__(self):
        self.n = [0,0]
        self.total = [0.,0.]

    def means(self):
        pooled = sum(self.total)/(16+sum(self.n))
        conditional = [(v+16*pooled)/(n+16) for n,v in zip(self.n,self.total)]
        return pooled,conditional

    def settle(self, event, normalized_return):
        i=int(event)
        self.total[i] += normalized_return
        self.n[i] += 1

    def predict(self, scale, probabilities):
        pooled,(survives,flips) = self.means()
        return {'zero':0.,'pooled':scale*pooled,
                **{k:scale*(survives+p*(flips-survives)) for k,p in probabilities.items()}}
