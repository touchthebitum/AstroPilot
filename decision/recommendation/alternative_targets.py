class AlternativeTargetEngine:

    @staticmethod
    def recommend(current_target, ranked_targets, max_results=3):

        alternatives = []

        for target in ranked_targets:

            if target["name"] == current_target:
                continue

            alternatives.append(target)

            if len(alternatives) >= max_results:
                break

        return alternatives