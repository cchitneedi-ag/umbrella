class MissingHeadReport:
    message = "Missing head report"


class MissingBaseCommit:
    message = "Invalid base commit"


class MissingHeadCommit:
    message = "Invalid head commit"


class MissingComparison:
    message = "Missing comparison"


class MissingBaseReport:
    message = "Missing base report"


class MissingCoverage:
    def __init__(self, message="Missing coverage"):
        self.message = message


class UnknownPath:
    def __init__(self, message="Unkown path"):
        self.message = message


class ProviderError:
    message = "Error fetching data from the provider"


# Currently unused, but I can leave it here if we use it eventually
class QueryError:
    def __init__(self, message):
        self.message = message
