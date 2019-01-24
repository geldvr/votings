class InvalidInputException(Exception):
    def __init__(self, field, message, payload=None):
        Exception.__init__(self)
        self.field = field
        self.message = message
        self.payload = payload

    def to_dict(self):
        dict_response = dict(self.payload or ())
        dict_response['field'] = self.field
        dict_response['message'] = self.message
        dict_response['status'] = False
        return dict_response
