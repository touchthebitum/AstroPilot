class BaseRule:
    """Base class for every decision rule."""

    def evaluate(self, project, context):
        raise NotImplementedError