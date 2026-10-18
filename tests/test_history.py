import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import app as fh
import history_store as store

C = {'origin':'CDG','destination':'PVG','departure':'2027-07-29','return':'2027-08-20',
     'adults':2,'children_ages':[{'age':8,'seat':True}],'stops':'any'}
OFFERS = [{'id':'a'*24,'carrier':'Test Airline','price':2093,
           'booking_token':'SECRET_BOOKING_TOKEN','outbound':{'stops':1},'inbound':{'stops':1},
           'booking_link':'https://www.google.com/travel/flights'}]

class SavedSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name)/'flight-history.sqlite3')
        self.vars = patch.dict(os.environ,{'FLIGHTHUNTER_HISTORY_SQLITE':self.path,'DATABASE_URL':''})
        self.vars.start()
        self.key = patch.object(fh,'API_KEY','test_api_key')
        self.code = patch.object(fh,'ACCESS_CODE','private')
        self.key.start();self.code.start()
        fh.CACHE.clear();fh.RATE.clear()
    def tearDown(self):
        self.code.stop();self.key.stop();self.vars.stop();self.temp.cleanup()
    def request(self, method, path, **kwargs):
        async def go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fh.app),base_url='https://app.test') as client:
                return await client.request(method,path,**kwargs)
        return asyncio.run(go())
    @property
    def auth(self):
        return {'X-Access-Code':'private'}

    def test_history_authentication_and_route_privacy(self):
        self.assertEqual(self.request('GET','/api/history').status_code,401)
        self.assertEqual(self.request('GET','/api/history/'+'a'*24).status_code,401)
        self.assertEqual(self.request('DELETE','/api/history/'+'a'*24).status_code,401)
        self.assertEqual(self.request('POST','/api/history/'+'a'*24+'/refresh').status_code,401)
        self.assertEqual(self.request('GET','/api/history/notavalidid',headers=self.auth).status_code,404)
        self.assertEqual(self.request('GET','/r/'+'b'*24).status_code,200)
        self.assertNotIn('Test Airline',self.request('GET','/r/'+'b'*24).text)

    def test_save_list_restore_delete(self):
        result={'criteria':fh.validate(C),'offers':OFFERS,'links':[{'google':'https://www.google.com/travel/flights'}],
                'status':'ok','checked_at':'2026-10-18T03:00:00+00:00','warning':'Confirm final prices'}
        result['offers'][0]['booking_token']='SECRET_BOOKING_TOKEN'
        identifier=store.save(result)
        self.assertRegex(identifier,r'^[a-f0-9]{24}$')
        self.assertEqual(len(store.list_recent()),1)
        row=self.request('GET','/api/history/'+identifier,headers=self.auth)
        self.assertEqual(row.status_code,200)
        self.assertEqual(row.json()['record']['snapshot']['offers'][0]['price'],2093)
        self.assertNotIn('SECRET_BOOKING_TOKEN',row.text)
        self.assertEqual(row.json()['record']['snapshot']['criteria']['children_ages'][0]['age'],8)
        self.assertEqual(len(self.request('GET','/api/history',headers=self.auth).json()['items']),1)
        self.assertEqual(self.request('DELETE','/api/history/'+identifier,headers=self.auth).status_code,200)
        self.assertEqual(self.request('GET','/api/history/'+identifier,headers=self.auth).status_code,404)

    def test_authenticated_search_saves_and_caches_same_link(self):
        with patch.object(fh,'serpapi_query',return_value={}),patch.object(fh,'price_offers',return_value=OFFERS):
            first=self.request('POST','/api/search',json=C,headers=self.auth)
            self.assertEqual(first.status_code,200)
            i=first.json()['history_id']
            self.assertEqual(first.json()['history_url'],'/r/'+i)
            self.assertEqual(len(store.list_recent()),1)
            again=self.request('POST','/api/search',json=C,headers=self.auth)
            self.assertTrue(again.json()['from_cache'])
            self.assertEqual(again.json()['history_id'],i)
            self.assertEqual(len(store.list_recent()),1)

    def test_refresh_preserves_old_snapshot_and_creates_new_one(self):
        result={'criteria':fh.validate(C),'offers':OFFERS,'links':[],
                'status':'ok','checked_at':'2026-10-18T03:00:00+00:00'}
        original=store.save(result)
        with patch.object(fh,'serpapi_query',return_value={}),patch.object(fh,'price_offers',return_value=[{**OFFERS[0],'price':2150}]):
            response=self.request('POST','/api/history/'+original+'/refresh',headers=self.auth)
        self.assertEqual(response.status_code,200)
        self.assertNotEqual(response.json()['history_id'],original)
        self.assertEqual(len(store.list_recent()),2)
        self.assertEqual(store.get(original)['snapshot']['offers'][0]['price'],2093)
        self.assertEqual(store.get(response.json()['history_id'])['snapshot']['offers'][0]['price'],2150)

    def test_failed_database_save_never_breaks_search(self):
        with patch.object(fh,'serpapi_query',return_value={}),patch.object(fh,'price_offers',return_value=OFFERS),patch.object(store,'save',side_effect=RuntimeError('SQL secrets')):
            r=self.request('POST','/api/search',json=C,headers=self.auth)
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json()['history_saved'])
        self.assertNotIn('SQL secrets',r.text)

    def test_wrong_code_never_reveals_saved_data(self):
        result={'criteria':fh.validate(C),'offers':OFFERS,'links':[],
                'status':'ok','checked_at':'2026-10-18T03:00:00+00:00'}
        identifier=store.save(result)
        bad={'X-Access-Code':'bad'}
        self.assertEqual(self.request('GET','/api/history',headers=bad).status_code,401)
        self.assertEqual(self.request('GET','/api/history/'+identifier,headers=bad).status_code,401)

    def test_login_cookie_allows_history_read(self):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fh.app),base_url='https://app.test') as c:
                before=await c.get('/api/history')
                login=await c.post('/api/session/login',json={'code':'private'})
                after=await c.get('/api/history')
                return before,login,after
        before,login,after=asyncio.run(run())
        self.assertEqual(before.status_code,401)
        self.assertEqual(login.status_code,200)
        self.assertIn('httponly',login.headers['set-cookie'].lower())
        self.assertEqual(after.status_code,200)

if __name__=='__main__':unittest.main()
