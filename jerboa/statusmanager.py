

class StatusManager(object):
    statuses = {
        '1': ('Successfully completed operation', 'success'),
        '2': ('Failed to complete operation.', 'alert'),
    }

    @classmethod
    def add_status(cls, message, status_type):
        new_code = str(len(cls.statuses)+1)
        cls.statuses[new_code] = (message, status_type)
        return new_code


def parse_request_status_code(request, response):
    request_status_code = request.GET.get('status_code', False)
    if not request_status_code:
        return

    try:
        response.raw.status_message = StatusManager.statuses[request_status_code]
    except KeyError:
        pass
    else:
        response.raw.status_code = request_status_code
