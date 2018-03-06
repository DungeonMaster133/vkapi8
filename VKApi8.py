import time
import random
import re
import json
import itertools
import xml.etree.ElementTree as ET
import datetime
import pprint

import requests
from html.parser import HTMLParser
from urllib.parse import urlparse
import urllib.request, urllib.parse, urllib.error
import urllib.request, urllib.error, urllib.parse
import http.cookiejar

class VKApi():
    def __init__(self, login, password, client, scope='', version='5.69', session=requests.Session()):
        self.token = self.get_token(login, password, client, 'offline' + (',' if scope!='' else '') + scope)[0]
        self.version = '5.69'
        self.session = session
        self.pp = pprint.PrettyPrinter(depth=1)

    def send_fake_request(self):
        _fake_requests_methods = {
            'database.getCities':'country_id',
            'database.getChairs':'faculty_id',
            'groups.getById':'group_id'
        }
        rand = random.randint(0, len(_fake_requests_methods)-1)
        method=list(_fake_requests_methods.keys())[rand]
        req_url = 'https://api.vk.com/method/{method_name}?{parameters}&v={api_v}'.format(
            method_name=method,
            api_v=self.version , parameters=_fake_requests_methods[method] + ':' + str(random.randint(1, 100)))
        self.session.get(req_url)


    def get_region(self, q, city_id):
        url = 'https://api.vk.com/method/database.getCities?country_id=1&q={}&v={}' 
        json_response = self.session.get(url.format(q, self.version)).json()
        time.sleep(0.34)
        if json_response.get('error'):
            print(json_response.get('error'))
            raise Exception("Error while getting region, error_code=" + str(json_response['error']['error_code']))
        if len(json_response['response']['items']) == 0:
            return None
        for item in json_response["response"]["items"]:
            if 'region' in item:
                if item["id"] == city_id: 
                    return item["region"]
        return json_response['response']['items'][0]["title"]

    def _get_group_25k_members(self, group_id, fields="", offset=0):
        code = '''var group = "''' + str(group_id) +  '''";
        var i = 0;
        var count = 25000;
        var ret = {};
        var data = {};
        while (i < 25 && i*1000 < count)
        {
            data = API.groups.getMembers({"group_id":group, "count":1000, "offset":i*1000 + ''' + str(offset) + ''', "fields":"''' + fields + '''"});
            count = data["count"];
            ret.push(data["items"]);
            i=i+1;
        }
        return {"count":count, "items":ret};'''
        resp = self.execute(code)
        if('error' in resp):
            raise Exception('Error while getting group_members, error: ' + str(resp['error']))
        membs = []
        for ar in resp['response']["items"]:
            membs.extend(ar)
        return {"count":resp['response']['count'], "items":membs}

    def get_all_group_members(self, group_id, fields=""):
        group_id=self.group_url_to_id(group_id)
        print('Getting ' + str(group_id) + ' members')
        members = self._get_group_25k_members(group_id, fields)
        if(members['count']>25000):
            for i in range(members['count']//25000 - int(members['count']%25000 == 0)):
                print('Getting ' + str(group_id) + ' members ' + 'iteration ' + str(i))
                members['items'].extend(self._get_group_25k_members(group_id, fields, (i+1)*25000)['items'])
        return members

    def _get_25_groups_members(self, group_ids, fields=""):
        code = '''var groups = ''' + str(group_ids).replace('\'', '"') +  ''';
        var i = 0;
        var ret = {};
        while (i < 25 && i < groups.length)
        {
            ret.push({"id":groups[i], "response":API.groups.getMembers({"group_id":groups[i], "count":1000, "fields":"''' + fields + '''"})});
            i=i+1;
        }
        return ret;'''
        resp = self.execute(code)
        if('error' in resp):
            raise Exception('Error while getting groups_members, error: ' + str(resp['error'])) 
        groups_data = {}
        for el in resp['response']:
            groups_data[el['id']] = el['response']
        for group_id, group_data in groups_data.items():
            if(group_data['count'] > 25000):
                groups_data[group_id] = self.get_all_group_members(group_id, fields)
        return groups_data

    def get_groups_members(self, group_ids, fields=""):
        group_ids = [self.group_url_to_id(group) for group in group_ids]
        members = self._get_25_groups_members(group_ids[:25], fields)
        if(len(group_ids)>25):
            for i in range(len(group_ids)//25 - int(len(group_ids)%25 == 0)):
                members.update(self._get_25_groups_members(group_ids[(i+1)*25:(i+2)*25], fields))
        return members

    def get_token(self, email, password, client_id, scope):
        class FormParser(HTMLParser):
            def __init__(self):
                HTMLParser.__init__(self)
                self.url = None
                self.params = {}
                self.in_form = False
                self.form_parsed = False
                self.method = "GET"

            def handle_starttag(self, tag, attrs):
                tag = tag.lower()
                if tag == "form":
                    if self.form_parsed:
                        raise RuntimeError("Second form on page")
                    if self.in_form:
                        raise RuntimeError("Already in form")
                    self.in_form = True
                if not self.in_form:
                    return
                attrs = dict((name.lower(), value) for name, value in attrs)
                if tag == "form":
                    self.url = attrs["action"]
                    if "method" in attrs:
                        self.method = attrs["method"].upper()
                elif tag == "input" and "type" in attrs and "name" in attrs:
                    if attrs["type"] in ["hidden", "text", "password"]:
                        self.params[attrs["name"]] = attrs["value"] if "value" in attrs else ""

            def handle_endtag(self, tag):
                tag = tag.lower()
                if tag == "form":
                    if not self.in_form:
                        raise RuntimeError("Unexpected end of <form>")
                    self.in_form = False
                    self.form_parsed = True
        
        def split_key_value(kv_pair):
            kv = kv_pair.split("=")
            return kv[0], kv[1]

        # Authorization form
        def auth_user(email, password, client_id, scope, opener):
            response = opener.open(
                "https://oauth.vk.com/oauth/authorize?" + \
                "redirect_uri=http://oauth.vk.com/blank.html&response_type=token&" + \
                "client_id=%s&scope=%s&display=wap" % (client_id, ",".join(scope))
                )
            doc = response.read()
            parser = FormParser()
            parser.feed(doc.decode("utf-8"))
            parser.close()
            if not parser.form_parsed or parser.url is None or "pass" not in parser.params or \
              "email" not in parser.params:
                raise RuntimeError("Something wrong")
            parser.params["email"] = email
            parser.params["pass"] = password
            if parser.method == "POST":
                response = opener.open(parser.url, urllib.parse.urlencode(parser.params).encode("utf-8"))
            else:
                raise NotImplementedError("Method '%s'" % parser.method)
            return response.read(), response.geturl()

        # Permission request form
        def give_access(doc, opener):
            parser = FormParser()
            parser.feed(doc.decode("utf-8"))
            parser.close()
            if not parser.form_parsed or parser.url is None:
                raise RuntimeError("Something wrong")
            if parser.method == "POST":
                response = opener.open(parser.url, urllib.parse.urlencode(parser.params).encode("utf-8"))
            else:
                raise NotImplementedError("Method '%s'" % parser.method)
            return response.geturl()

        if not isinstance(scope, list):
            scope = [scope]
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPRedirectHandler())
        doc, url = auth_user(email, password, client_id, scope, opener)
        if urlparse(url).path != "/blank.html":
            # Need to give access to requested scope
            url = give_access(doc, opener)
        if urlparse(url).path != "/blank.html":
            raise RuntimeError("Expected success here")
        answer = dict(split_key_value(kv_pair) for kv_pair in urlparse(url).fragment.split("&"))
        if "access_token" not in answer or "user_id" not in answer:
            raise RuntimeError("Missing some values in answer")
        return answer["access_token"], answer["user_id"]
        
    def validate_users(self, user_ids):
        ret_ids = []
        new_users = self.get_users_data(user_ids, '')
        for user in new_users:
            if('deactivated' not in user):
                ret_ids.append(user['id'])
        return ret_ids

    def get_users_data(self, user_ids, fields, format='csv', _opti=300):
        if(format != "csv" and format != "xml"):
            raise Exception('Error while getting users information, wrong format given: "' + format + '"')
        url_xml = 'https://api.vk.com/method/users.get.xml?user_ids={}&fields={}&access_token={}&v={}'
        url = 'https://api.vk.com/method/users.get?user_ids={}&fields={}&access_token={}&v={}'
        iterations = (len(user_ids) // _opti) + (1 if(len(user_ids)%_opti) else 0)

        if(format == 'xml'):
            user_data = "<?xml version='1.0' encoding='utf8'?>\n<users>\n"
        else:
            user_data = []    
        
        for i in range(iterations):
            print(str(i+1) + " of " + str(iterations))
            try:
                if((len(user_ids) - _opti*i) < _opti):
                    ids = user_ids[_opti*i:]
                else:
                    ids = user_ids[_opti*i:(_opti*(i+1))]
            except:
                break
            if(format == "xml"):
                response = self.session.get(url_xml.format(str(ids).replace("[", "").replace("]", ""), fields, self.token, self.version)).text
                root = ET.fromstring(response)
                if(root[0].tag == 'error_code'):
                    raise Exception('Error while getting users information, error_code=' + str(root[0].text))
                for child in root:
                    user_data += ET.tostring(child, encoding='utf8', method='xml').decode('utf-8').replace("<?xml version='1.0' encoding='utf8'?>", "")
            else:
                response = self.session.get(url.format(str(ids).replace("[", "").replace("]", ""), fields, self.token, self.version)).json()
                if('error' in response):
                    raise Exception('Error while getting users information, error_code=' + str(response['error']['error_code']))
                user_data.extend(response['response'])
            time.sleep(0.34)
        return user_data

    def get_users_sequence_generator(self, from_id, to_id, fields):
        url = 'https://api.vk.com/method/users.get?user_ids={}&fields={}&access_token={}&v={}'
        _opti = 300
        iterations = (to_id-from_id) // _opti + 1
        for i in range(iterations):
            if(i%15+1==0):
                self.send_fake_request()
                time.sleep(1)
            print(str(i+1) + " of " + str(iterations))
            ids = list(range(i*_opti+from_id, (i+1)*_opti+from_id))
            if(to_id - (i*_opti+from_id) < _opti):
                ids=ids[:to_id - (i*_opti+from_id)]
            response = self.session.get(url.format(str(ids).replace("[", "").replace("]", ""), fields, self.token, self.version)).json()
            if('error' in response):
                raise Exception('Error while getting users information, error_code=' + str(response['error']['error_code']))
            yield response['response']

    """def get_users_in_seq(self, id_from, id_to, fields, format='csv'):
        if(format != "csv" and format != "xml"):
            raise Exception('Error while getting users information, wrong format given: "' + format + '"')
        _opti = 25000
        iterations = (id_to-id_from // _opti) + 1
        if(format == 'xml'):
            user_data = "<?xml version='1.0' encoding='utf8'?>\n<users>\n"
        else:
            user_data = []
        code = '''
        var from = {:d};
        var to = {:d};
        var ids = [];
        while(from!=to && ids.length<25000)
        {{
            ids.push(from);
            from=from+1;
        }}
        var i = 0;
        var count = ids.length;
        var ret = [];
        var users = [];
        while (i < 25 && i*1000 < count)
        {{
            users = ids.slice(i*1000, (i+1)*1000);
            ret.push(API.users.get''' + ('.xml' if(format=='xml') else '') + '''({{"user_ids": users, "count":1000,  "fields":"''' + fields + '''"}}));
        i=i+1;
        }}
        return ret;
        '''
        for i in range(iterations):
            print(str(i+1) + " of " + str(iterations))
            _id_to = (id_from + _opti) if((id_to-id_from)>_opti) else id_to
            #resp = self.execute(code.replace('{ids}', str(user_ids)))
            resp = self.execute(code.format(id_from, _id_to))
            if('error' in resp):
                raise Exception('Error while getting group_members, error: ' + str(resp['error']))
            users = []
            for ar in resp['response']:
                users.extend(ar)
            if(format == "xml"):
                response = resp.text
                root = ET.fromstring(response)
                if(root[0].tag == 'error_code'):
                    raise Exception('Error while getting users information, error=' + str(root[0].text))
                for child in root:
                    user_data += ET.tostring(child, encoding='utf8', method='xml').decode('utf-8').replace("<?xml version='1.0' encoding='utf8'?>", "")
            else:
                user_data.extend(resp['response'])
            id_from = _opti
        return user_data"""

    def _get_user_groups_by_offset(self, id, offset=0):
        url = 'https://api.vk.com/method/groups.get?user_id={}&access_token={}&offset={}&count=1000&v={}'
        json_response = self.session.get(url.format(id,self.token, offset, self.version)).json()
        time.sleep(0.34)
        if 'error' in json_response:
            raise Exception('Error while getting group members, error=' + str(json_response['error']))
        return json_response['response']

    def get_user_groups(self, id):
        id = self.user_url_to_id(id)
        groups = self._get_user_groups_by_offset(id)
        if(groups['count']>1000):
            iterations = int(groups['count']/1000) - int(groups['count']%1000 == 0)
            for i in range(iterations):
                groups['items'].extend(self._get_user_groups_by_offset(id, 1000*i)['items'])
        return groups

    def execute(self, code):
        resp = self.session.post('https://api.vk.com/method/execute', data={'access_token':self.token, 'code':code, 'v':self.version})
        time.sleep(0.34)
        if(resp.status_code != 200):
            raise Exception('Network error, error code: ' + str(resp.status_code))
        return resp.json()

    def _get_25_users_subscriptions(self, ids):
        code = '''var ids = ''' + str(ids).replace('\'', '"') +  ''';
        var i = 0;
        var ret = {};
        while (i < 25 && i < ids.length)
        {
            ret.push({"id":ids[i], "response":API.users.getSubscriptions({"user_id":ids[i], "extended":0, "count":200})});
            i=i+1;
        }
        return ret;'''
        resp = self.execute(code)
        if('error' in resp):
            raise Exception('Error while getting 25_users_groups, error: ' + str(resp['error'])) 
        users_data = {}
        for el in resp['response']:
            if(el['response'] == False or el['response'] == False):
                users_data[el['id']] = None
                continue
            users_data[el['id']] = el['response']
        return users_data

    def _get_25_users_groups(self, ids):
        code = '''var ids = ''' + str(ids).replace('\'', '"') +  ''';
        var i = 0;
        var ret = {};
        while (i < 25 && i < ids.length)
        {
            ret.push({"id":ids[i], "response":API.groups.get({"user_id":ids[i], "extended":1, "count":500})});
            i=i+1;
        }
        return ret;'''
        resp = self.execute(code)
        if('error' in resp):
            raise Exception('Error while getting 25_users_groups, error: ' + str(resp['error'])) 
        users_data = {}
        for el in resp['response']:
            if(el['response'] == False or el['response'] == False):
                users_data[el['id']] = None
                continue
            user_groups = []
            for group in el['response']['items']:
                if(group['type']=='group'):
                    user_groups.append(group['id'])
            users_data[el['id']] = {'count':len(user_groups), 'items':user_groups}
        return users_data    

    def _get_25_users_friends(self, ids):
        code = '''var ids = ''' + str(ids).replace('\'', '"') +  ''';
        var i = 0;
        var ret = {};
        while (i < 25 && i < ids.length)
        {
            ret.push({"id":ids[i], "response":API.friends.get({"user_id":ids[i], "count":1000})});
            i=i+1;
        }
        return ret;'''
        resp = self.execute(code)
        if('error' in resp):
            raise Exception('Error while getting 25_users_friends, error: ' + str(resp['error'])) 
        users_data = {}
        for el in resp['response']:
            if(el['response'] == False or el['response'] == False):
                users_data[el['id']] = None
                continue
            if(el['response']['count'] > 1000):
                users_data[el['id']] = self.get_friends_ids(el['id'])
            else:
                users_data[el['id']] = el['response']
        return users_data

    def _get_25_users_subs(self, ids):
        code = '''var ids = ''' + str(ids).replace('\'', '"') +  ''';
        var i = 0;
        var ret = {};
        while (i < 25 && i < ids.length)
        {
            ret.push({"id":ids[i], "response":API.users.getFollowers({"user_id":ids[i], "count":1000})});
            i=i+1;
        }
        return ret;'''
        resp = self.execute(code)
        if('error' in resp):
            raise Exception('Error while getting 25_users_subs, error: ' + str(resp['error'])) 
        users_data = {}
        for el in resp['response']:
            if(el['response'] == False or el['response'] == False):
                users_data[el['id']] = None
                continue
            if(el['response']['count'] > 1000):
                users_data[el['id']] = self.load_all_subs(el['id'])
            else:
                users_data[el['id']] = el['response']
        return users_data

    def get_users_extended_info(self, ids, infos):
        methods = {
            "friends":self._get_25_users_friends,
            "subs":self._get_25_users_subs,
            "publics":self._get_25_users_subscriptions,
            "groups":self._get_25_users_groups
        }
        methods_to_apply = []
        for info in infos:
            if(info in methods):
                methods_to_apply.append((info, methods[info]))
        i = iter(ids)
        ids_to_aggregate = list(itertools.islice(i, 0, 25))
        while(ids_to_aggregate):
            yield_data = {}
            for agr_info, method in methods_to_apply:
                new_data = None
                while not new_data:
                    #try:
                    new_data = method(ids_to_aggregate)
                    #except:
                        #print('Something wrong, waiting...')
                        #time.sleep(3)
                for user, data in new_data.items():
                    try:
                        yield_data[user][agr_info] = data
                    except:
                        yield_data[user] = {agr_info:data}
            ids_to_aggregate = list(itertools.islice(i, 0, 25))
            yield yield_data

    def get_posts_by_offset(self, user_id, offset, count, flag, domain):
        if (domain):
            url = 'https://api.vk.com/method/wall.get?domain={}&offset={}&count={}&access_token={}&v=5.60'
            users = self.session.get(url.format(user_id, offset, count, self.token)).json()
        else:
            url = 'https://api.vk.com/method/wall.get?owner_id={}&offset={}&count={}&access_token={}&v=5.60'
            users = self.session.get(url.format(user_id, offset, count, self.token)).json()
        if users.get('error'):
            print(users.get('error')["error_msg"])
            return -1
        if flag == "count":
            return users[u'response']["count"]
        else:
            return users[u'response']["items"]

    def get_posts(self, user_id, domain=False):
        text = {"author_text": "", "copy_text": "", "posts_count": 0, "reposts_count": 0}
        total_posts_count = self.get_posts_by_offset(user_id, 0, 0, "count", domain)
        text["posts_count"] = total_posts_count
        posts_count = 0
        offset = 0
        while posts_count < total_posts_count:
            time.sleep(0.34)
            posts = self.get_posts_by_offset(user_id, offset, 50, "", domain)
            offset += 50
            print('Got {} posts out of {}'.format(offset, total_posts_count))
            for item in posts:
                if item["text"] != "":
                    text["author_text"] = text["author_text"] + item[
    					"text"] + "\n####################################################\n"
                if  "copy_history" in item.keys():
                    text["reposts_count"] = text["reposts_count"] + 1
                    if item["copy_history"][0]["text"] != "":
                        text["copy_text"] = text["copy_text"] + item["copy_history"][0][
    						"text"] + "\n####################################################\n"
                posts_count += 1
        return text

    def group_url_to_id(self, group_url):
        group_url = str(group_url)
        parts = group_url.split("/")
        if(len(parts) != 1):
            group_url = parts[-1:][0]
        groupId = group_url.strip()
        if(re.match(r'(club|public)\d', groupId) != None):
            groupId = re.search(r'\d.*', groupId).group(0)
        return groupId

    def user_url_to_id(self, user_url):
        user_url = str(user_url)
        parts = user_url.split('/')
        if(len(parts) != 1):
            user_url = parts[-1:]
        user_id = user_url.strip()
        if(re.match(r'id\d*', user_id) != None):
            user_id = re.search(r'\d.*', user_id).group(0)
        return user_id
        
    def get_user_id(self, link):
        users_url = 'https://api.vk.com/method/users.get?user_ids={}&access_token={}&v={}'
        domain = link.split("/")[-1]
        json_response = self.session.get(users_url.format(domain, self.token, self.version)).json()
        time.sleep(0.34)
        if json_response.get('error'):
            raise Exception('Error while getting friends urls, error_code=' + str(json_response['error']['error_code']))
        return json_response[u'response'][0]['id']

    def _load_25k_subs(self, id, offset=0):
        code = '''var user = ''' + str(id) + ''';
        var i = 0;
        var ret = [];
        var count = 25000;
        var data = {};
        while (i*1000 < count &&  i<25)
        {
            data = API.users.getFollowers({"user_id":user, "count":1000, "offset":i*1000 + ''' + str(offset) + '''});
            count = data["count"];
            ret.push(data["items"]);
            i=i+1;
        }
        return {"count":count, "items":ret};'''
        resp = self.execute(code)
        if(resp['response']['count'] == None):
            return {'count':None, 'items':None}
        if('error' in resp):
            raise Exception('Error while getting 25k subs, error: ' + str(resp['error']))
        subs = []
        for ar in resp['response']['items']:
            subs.extend(ar)
        if('execute_errors' in resp):
            pass
        return {'count':resp['response']['count'], 'items':subs}

    def load_all_subs(self, id):
        id = self.user_url_to_id(id)
        subs = self._load_25k_subs(id)
        count = subs['count']
        if(count == None):
            return None
        for i in range(count//25000 - int(count%25000 == 0)):
            subs['items'].extend(self._load_25k_subs(id, i*25000))
        return subs

    def get_friends_ids(self, id, count=25000):
        id = self.user_url_to_id(id)
        code = '''var user = ''' + str(id) + ''';
        var i = 0;
        var ret = [];
        var count = ''' + str(count) + ''';
        var data = {};
        while (i*1000 < count)
        {
            data = API.friends.get({"user_id":user, "count":1000, "offset":i*1000});
            count = data["count"];
            ret.push(data["items"]);
            i=i+1;
        }
        return {"count":count, "items":ret};'''
        resp = self.execute(code)
        if('error' in resp):
            raise Exception('Error while getting all friends, error: ' + str(resp['error']))
        if(resp['response']['count'] == None):
            return None 
        friends = []
        for ar in resp['response']['items']:
            friends.extend(ar)
        if('execute_errors' in resp):
            pass
        return {"count": resp['response']['count'], "items":friends}

    def _get_10k_messages(self, peer_id, date=time.strftime("%d%m%Y"), _offset=0):
        messages = {}
        filtered=0
        for i in range(4):
            code = '''var peer_id = ''' + str(peer_id) + ''';
            var i = 0;
            var ret = [];
            var count = 10000;
            var data = [];
            var date = ''' + date + ''';
            while (i*100 + {offset} < count && i<25)
            {{
                data = API.messages.search({{"peer_id":peer_id, "date":date, "count":100, "offset":i*100 + {offset}}});
                count = data["count"];
                ret.push(data["items"]);
                if(data["items"].length == 0){{
                    return {{"count":count, "items":ret}};
                }}
                i=i+1;
            }}
            return {{"count":count, "items":ret}};'''.format(offset=i*2500+_offset)
            resp = self.execute(code)
            if('error' in resp):
                raise Exception('Error while getting all friends, error: ' + str(resp['error']))
            for ar in resp['response']['items']:
                for message in ar:
                    if('body' in message and message['body']!=''):
                        messages[message['id']] = {'body':message['body'], 'date':message['date'], 'user_id':message['user_id']}
                    else:
                        filtered+=1
            if(not len(resp['response']['items']) or not len(resp['response']['items'][0])):
                break
            self.send_fake_request()
        return {"count": resp['response']['count'], "filtered":filtered, "items":messages}

    def get_all_messages_generator(self, peer_id, opti=7500, limit=7500):
        count = 10000
        j = 0
        date=time.strftime("%d%m%Y")
        while j<count and j*opti<limit:
            i = 0
            messages = {}
            while len(messages)<opti and i<count and i<opti:
                new_messages = self._get_10k_messages(peer_id, date, i)
                if(len(new_messages['items']) == 0):
                    j = count
                    break
                count = new_messages['count']
                i+=len(new_messages['items']) + new_messages['filtered']
                messages.update(new_messages['items'])
            if(len(messages)==0):
                yield {}    
                break
            time.sleep(1)
            self.send_fake_request()
            date = datetime.datetime.fromtimestamp(messages[min(list(messages.keys()))]['date']).strftime('%d%m%Y')
            j+=i
            yield messages
    
    # Finally, some good fucking code
    def get_some_good_fucking_code(self):
        return '<?php /** * Created by PhpStorm. * User: Sergey * Date: 16.02.2018 * Time: 15:25 */ echo "asd"; '
