# VKApi8, Python3 based

Usage:
```Python3
from vk_api8 import VKApi

login = "+78005553535"
password = "shashlichok72"
client = "12345678" #VK App client id
scope = "friends,messages,groups" #OPTIONAL
version = "5.69" #Api version OPTIONAL
session = requests.Session() #OPTIONAL

api = VKApi(login, password, client, scope, version, session)

id = 125341435
user_friends = api.get_friends_ids(id)
friends_count = user_friends['count']
friends_ids = user_friends['items']```

Instalation:
--------------------
pip3 install vkapi8
