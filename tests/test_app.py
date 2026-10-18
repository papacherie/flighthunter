import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import httpx
import app as fh

C = {'origin': 'CDG,ORY', 'destination': 'PVG,SHA', 'departure': '2027-07-29',
     'return': '2027-08-20', 'adults': 2, 'children_ages': [{'age': 8}], 'stops': '1'}

OUTBOUND = {'flights': [
    {'departure_airport': {'id': 'CDG', 'time': '2027-07-29 10:50'},
     'arrival_airport': {'id': 'BAH', 'time': '2027-07-29 18:00'}, 'airline': 'Gulf Air', 'flight_number': 'GF 12'},
    {'departure_airport': {'id': 'BAH', 'time': '2027-07-29 21:00'},
     'arrival_airport': {'id': 'PVG', 'time': '2027-07-30 11:55'}, 'airline': 'Gulf Air', 'flight_number': 'GF 124'}],
    'total_duration': 1145, 'price': 2093, 'departure_token': 'validtoken123',
    'layovers': [{'id': 'BAH', 'duration': 180}]}
RETURN = {'flights': [
    {'departure_airport': {'id': 'PVG', 'time': '2027-08-20 15:55'},
     'arrival_airport': {'id': 'BAH', 'time': '2027-08-20 20:50'}, 'airline': 'Gulf Air', 'flight_number': 'GF 121'},
    {'departure_airport': {'id': 'BAH', 'time': '2027-08-20 23:55'},
     'arrival_airport': {'id': 'CDG', 'time': '2027-08-21 07:55'}, 'airline': 'Gulf Air', 'flight_number': 'GF 11'}],
    'total_duration': 1205, 'price': 2113, 'layovers': [{'id': 'BAH', 'duration': 150}],
    'booking_token': 'bookingTokenIsNotExposed'}


class FlightHunterTests(unittest.TestCase):
    def request(self, method, path, **kwargs):
        async def go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fh.app), base_url='http://test') as c:
                return await c.request(method, path, **kwargs)
        return asyncio.run(go())

    def setUp(self):
        fh.CACHE.clear()
        fh.RATE.clear()

    def test_v5_ui_assets_and_logo_csp(self):
        resp = self.request('GET', '/')
        self.assertIn('v=6.0.0', resp.text)
        self.assertIn('id="passenger-popover"', resp.text)
        self.assertIn('id="calendar-panel"', resp.text)
        self.assertNotIn('SERPAPI_API_KEY=', resp.text)
        self.assertIn('https://www.gstatic.com', resp.headers['content-security-policy'])

    def test_health(self):
        self.assertEqual(self.request('GET', '/health').json()['ok'], True)
        self.assertEqual(self.request('GET', '/').status_code, 200)

    def test_links_without_key(self):
        with patch.object(fh, 'API_KEY', ''), patch.object(fh, 'ACCESS_CODE', ''):
            r = self.request('POST', '/api/search', json=C)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'not_configured')
        self.assertEqual(r.json()['offers'], [])
        self.assertEqual(len(r.json()['links']), 1)

    def test_missing_code_blocks_api(self):
        with patch.object(fh, 'API_KEY', 'a_fake_test_key'), patch.object(fh, 'ACCESS_CODE', ''):
            r = self.request('GET', '/api/status')
            self.assertTrue(r.json()['needs_access_code'])
            self.assertFalse(r.json()['ready'])

    def test_serpapi_parameters(self):
        with patch.object(fh, 'API_KEY', 'mock'):
            p = fh.serpapi_parameters(fh.validate(C))
        self.assertEqual(p['engine'], 'google_flights')
        self.assertEqual(p['departure_id'], 'CDG,ORY')
        self.assertEqual(p['arrival_id'], 'PVG,SHA')
        self.assertEqual(p['adults'], 2)
        self.assertEqual(p['children'], 1)
        self.assertEqual(p['stops'], 2)

    def test_return_flight_verified_and_sorted(self):
        with patch.object(fh, 'serpapi_query', return_value={'other_flights': [RETURN]}) as provider:
            offers = fh.price_offers({'best_flights': [OUTBOUND]}, fh.validate(C))
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]['price'], 2113)
        self.assertEqual(offers[0]['outbound']['stops'], 1)
        self.assertEqual(offers[0]['inbound']['stops'], 1)
        self.assertEqual(provider.call_args[0][1], 'validtoken123')
        self.assertNotIn('validtoken123', str(offers))
        self.assertNotIn('bookingTokenIsNotExposed', str(offers))

    def test_logo_from_serpapi_and_fallback(self):
        from copy import deepcopy
        flight = deepcopy(OUTBOUND)
        flight['flights'][0]['airline_logo'] = 'https://www.gstatic.com/flights/airline_logos/70px/GF.png'
        logos = fh.leg_info(flight)['airline_logos']
        self.assertEqual(logos[0]['airline'], 'Gulf Air')
        self.assertEqual(logos[0]['code'], 'GF')
        self.assertEqual(logos[0]['url'], 'https://www.gstatic.com/flights/airline_logos/70px/GF.png')
        self.assertEqual(fh.leg_info(OUTBOUND)['airline_logos'][0]['url'], 'https://www.gstatic.com/flights/airline_logos/70px/GF.png')

    def test_invalid_logo_urls_rejected(self):
        for candidate in ('http://www.gstatic.com/flights/airline_logos/70px/GF.png',
                          'https://evil.example/flights/airline_logos/70px/GF.png',
                          'https://www.gstatic.com/other/payload.svg', 'javascript:alert(1)'):
            self.assertEqual(fh.safe_airline_logo(candidate), '')

    def test_public_links_do_not_use_serpapi(self):
        with patch.object(fh, 'serpapi_query') as fetch:
            r = self.request('POST', '/api/links', json=C)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['links']), 1)
        fetch.assert_not_called()

    def test_logo_payload_in_priced_offer(self):
        from copy import deepcopy
        flight = deepcopy(OUTBOUND)
        flight['flights'][0]['airline_logo'] = 'https://www.gstatic.com/flights/airline_logos/70px/GF.png'
        with patch.object(fh, 'serpapi_query', return_value={'other_flights': [RETURN]}):
            o = fh.price_offers({'best_flights': [flight]}, fh.validate(C))
        self.assertEqual(len(o), 1)
        self.assertEqual(o[0]['outbound']['airline_logos'][0]['code'], 'GF')
        self.assertEqual(o[0]['outbound']['segments'][0]['flight_number'], 'GF 12')

    def test_wrong_return_day_not_presented(self):
        invalid = {**RETURN, 'flights': [
            {**RETURN['flights'][0], 'departure_airport': {'id': 'PVG', 'time': '2027-08-21 15:55'}},
            RETURN['flights'][1]]}
        with patch.object(fh, 'serpapi_query', return_value={'best_flights': [invalid]}):
            offers = fh.price_offers({'other_flights': [OUTBOUND]}, fh.validate(C))
        self.assertEqual(offers, [])

    def test_bad_access_code_rejected_before_provider(self):
        with patch.object(fh, 'API_KEY', 'mock'), patch.object(fh, 'ACCESS_CODE', 'correct'):
            r = self.request('POST', '/api/search', json=C, headers={'X-Access-Code': 'wrong'})
        self.assertEqual(r.status_code, 401)

    def test_end_to_end_backend_mock(self):
        with patch.object(fh, 'API_KEY', 'mock'), patch.object(fh, 'ACCESS_CODE', 'correct'), \
             patch.object(fh, 'serpapi_query', side_effect=[{'best_flights': [OUTBOUND]}, {'other_flights': [RETURN]}]) as q:
            r = self.request('POST', '/api/search', json=C, headers={'X-Access-Code': 'correct'})
            self.assertEqual(r.status_code, 200)
            d = r.json()
            self.assertEqual(d['count'], 1)
            self.assertEqual(d['offers'][0]['price'], 2113)
            self.assertEqual(len(q.call_args_list), 2)
            r2 = self.request('POST', '/api/search', json=C, headers={'X-Access-Code': 'correct'})
            self.assertTrue(r2.json()['from_cache'])

    def test_arbitrary_airports_and_city_ids(self):
        other = dict(C, origin='JFK', destination='HND', children_ages=[{'age':5}, {'age':15}])
        c = fh.validate(other)
        self.assertEqual(c['origin'], 'JFK')
        self.assertEqual(c['destination'], 'HND')
        self.assertEqual(c['serpapi_adults'], 3)  # age 15 is priced in adult category
        self.assertEqual(c['children'], 1)
        self.assertEqual(c['travelers_count'], 4)
        self.assertEqual(fh.validate(dict(other, destination='/m/07dfk'))['destination'], '/m/07dfk')
        self.assertEqual(fh.serpapi_parameters(c)['arrival_id'], 'HND')

    def test_babies_ages_and_seats(self):
        c = fh.validate(dict(C, adults=2, children_ages=[{'age':0,'seat':False}, {'age':1,'seat':True}, {'age':12}, {'age':6}]))
        p = fh.serpapi_parameters(c)
        self.assertEqual((p['adults'],p['children'],p['infants_in_seat'],p['infants_on_lap']), (3,1,1,1))
        self.assertEqual(c['travelers_count'], 6)
        with self.assertRaises(ValueError):
            fh.validate(dict(C, adults=1, children_ages=[{'age':0,'seat':False}, {'age':1,'seat':False}]))

    def test_reject_invalid_airports_and_child_ages(self):
        for airport in ('', 'ANYWHERE', '../../../passwd', 'CDG;ORY'):
            with self.assertRaises(ValueError):
                fh.validate(dict(C, origin=airport))
        for ages in ([{'age':18}], [{'age':-1}], [{'age':'8'}], '8'):
            with self.assertRaises(ValueError):
                fh.validate(dict(C, children_ages=ages))
        with self.assertRaises(ValueError):
            fh.validate(dict(C, origin='JFK', destination='JFK'))

    def test_airports_requires_private_code_before_spending_credit(self):
        with patch.object(fh,'API_KEY','fake'), patch.object(fh,'ACCESS_CODE','private'), \
             patch.object(fh.requests,'get') as getter:
            response=self.request('GET','/api/airports?q=London')
            self.assertEqual(response.status_code, 401)
            getter.assert_not_called()

    def test_airport_autocomplete_matches_city_airport(self):
        body={'suggestions':[{'name':'London','id':'/m/04jpl',
                'airports':[{'name':'Heathrow Airport','id':'LHR'}, {'name':'Gatwick','id':'LGW'}]}]}
        class MockResponse:
            def raise_for_status(self): pass
            def json(self):return body
        with patch.object(fh,'API_KEY','fake'), patch.object(fh,'ACCESS_CODE','private'), \
             patch.object(fh.requests,'get',return_value=MockResponse()) as getter:
            response=self.request('GET','/api/airports?q=London',headers={'X-Access-Code':'private'})
            self.assertEqual(response.status_code,200)
            suggestions=response.json()['suggestions']
            self.assertEqual([x['id'] for x in suggestions],['/m/04jpl','LHR','LGW'])
            again=self.request('GET','/api/airports?q=London',headers={'X-Access-Code':'private'})
            self.assertTrue(again.json()['from_cache'])
            self.assertEqual(getter.call_count,1)

    def test_v6_blank_search_and_toggle_assets(self):
        r=self.request('GET','/')
        self.assertEqual(r.status_code,200)
        body=r.text
        for needle in ('v=6.0.0','id="theme-toggle"','id="origin"','id="destination"', 'id="departure"', 'id="return-date"'):
            self.assertIn(needle,body)
        self.assertNotIn('data-code="CDG,ORY"',body)
        self.assertNotIn('value="2027-07-29"',body)

    def test_v6_six_real_return_combinations(self):
        import copy
        data=copy.deepcopy(OUTBOUND)
        data['departure_token']='outbound6token'
        candidates=[]
        for i in range(6):
            flight=copy.deepcopy(RETURN)
            flight['price']=2100+i*25
            flight['booking_token']='booking'+str(i)
            flight['flights'][0]['flight_number']='GF '+str(120+i)
            flight['flights'][0]['departure_airport']['time']=f'2027-08-20 {10+i:02d}:55'
            candidates.append(flight)
        with patch.object(fh,'serpapi_query',return_value={'other_flights': candidates}) as provider:
            matches=fh.price_offers({'other_flights':[data]},fh.validate(C))
        self.assertEqual(len(matches),6)
        self.assertEqual([x['price'] for x in matches],[2100+i*25 for i in range(6)])
        self.assertTrue(all(x['direct_booking_available'] for x in matches))
        self.assertEqual(provider.call_count,1)
        self.assertTrue(all(x['id'] in fh.BOOKING_REFS for x in matches))

    def test_v6_no_invented_six_if_only_one_return(self):
        with patch.object(fh,'serpapi_query',return_value={'other_flights':[RETURN]}):
            matches=fh.price_offers({'other_flights':[OUTBOUND]},fh.validate(C))
        self.assertEqual(len(matches),1)

    def test_v6_airline_endpoint_requires_code_and_valid_id(self):
        with patch.object(fh,'API_KEY','mock'),patch.object(fh,'ACCESS_CODE','code'):
            r=self.request('POST','/api/airline-link',json={'offer_id':'whatever'})
            self.assertEqual(r.status_code,401)
            r=self.request('POST','/api/airline-link',json={'offer_id':'whatever'},headers={'X-Access-Code':'code'})
            self.assertEqual(r.status_code,400)
            r=self.request('POST','/api/airline-link',json={'offer_id':'a'*24},headers={'X-Access-Code':'code'})
            self.assertEqual(r.status_code,404)

    def test_v6_booking_provider_fallback(self):
        fid='b'*24
        fh.BOOKING_REFS[fid]=(fh.time.monotonic()+900,'booking_token','Gulf Air','https://www.google.com/travel/flights?hl=fr')
        with patch.object(fh,'API_KEY','mock'),patch.object(fh,'ACCESS_CODE','code'),patch.object(fh,'booking_options_for_token',return_value={'booking_options':[]}):
            r=self.request('POST','/api/airline-link',json={'offer_id':fid},headers={'X-Access-Code':'code'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['status'],'fallback')
        self.assertIn('www.google.com',r.json()['url'])

    def test_v6_rejects_untrusted_booking_request(self):
        self.assertIsNone(fh.google_booking_redirect({'url':'http://127.0.0.1/admin','post_data':'a=b'}))
        self.assertIsNone(fh.google_booking_redirect({'url':'https://evil.com','post_data':'x'}))
        self.assertIsNone(fh.google_booking_redirect({'url':'https://www.google.com/travel/clk/f'}))
        self.assertEqual(fh.google_booking_redirect({'url':'https://www.google.com/travel/clk/f?token=abc'}),'https://www.google.com/travel/clk/f?token=abc')

    def test_v6_session_login_and_cookie_auth(self):
        with patch.object(fh,'API_KEY','api-test'), patch.object(fh,'ACCESS_CODE','correct-code'):
            denied=self.request('POST','/api/session/login',json={'code':'wrong'})
            self.assertEqual(denied.status_code,401)
            allowed=self.request('POST','/api/session/login',json={'code':'correct-code'})
            self.assertEqual(allowed.status_code,200)
            cookie=allowed.cookies.get(fh.SESSION_COOKIE)
            self.assertTrue(cookie)
            self.assertIn('HttpOnly',allowed.headers['set-cookie'])
            self.assertIn('Secure',allowed.headers['set-cookie'])
            status=self.request('GET','/api/status',headers={'Cookie':fh.SESSION_COOKIE+'='+cookie})
            self.assertTrue(status.json()['authenticated'])
            bad=self.request('GET','/api/status',headers={'Cookie':fh.SESSION_COOKIE+'='+cookie+'x'})
            self.assertFalse(bad.json()['authenticated'])
            fh.CACHE.clear();fh.RATE.clear()
            with patch.object(fh,'serpapi_query',side_effect=[{'best_flights':[OUTBOUND]},{'other_flights':[RETURN]}]):
                r=self.request('POST','/api/search',json=C,headers={'Cookie':fh.SESSION_COOKIE+'='+cookie})
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.json()['count'],1)

    def test_v6_no_session_when_code_rotated(self):
        with patch.object(fh,'API_KEY','test-key'),patch.object(fh,'ACCESS_CODE','one'):
            token=fh.make_session_cookie()
        with patch.object(fh,'API_KEY','test-key'),patch.object(fh,'ACCESS_CODE','two'):
            denied=self.request('GET','/api/status',headers={'Cookie':fh.SESSION_COOKIE+'='+token})
            self.assertFalse(denied.json()['authenticated'])

if __name__ == '__main__':
    unittest.main()
