from pprint import PrettyPrinter

from vkapi8 import *
from .creds import login, password, client

printer = PrettyPrinter()
api = None


def test_init(scope='groups'):
    global api
    api = VKApi(login, password, client, scope, debug=True)


def test_get_groups_data():
    for chunk in api.get_groups_by_id_generator(list(range(1, 3000)),
                                                'description,age_limits,city,country,status'):
        printer.pprint(chunk[0])
