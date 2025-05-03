
class JSONable:
    """
    A base class for a model that is stored as a JSON column.
    """

    def dump(self):
        return self.__dict__

    @classmethod
    def load(cls, json_value):
        return cls(**json_value)

class DotDict(dict):
    """
    dot.notation access to dictionary attributes
    """

    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__
