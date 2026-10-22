"""Minimal Warcraft Logs v2 GraphQL client (client credentials flow).

Reads WCL_CLIENT_ID / WCL_CLIENT_SECRET from the environment. The token is kept
in memory only and never written to disk.
"""
import os
import time

import requests

TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
API_URL = "https://www.warcraftlogs.com/api/v2/client"


class WCLClient:
    def __init__(self, client_id=None, client_secret=None):
        self._id = client_id or os.environ["WCL_CLIENT_ID"]
        self._secret = client_secret or os.environ["WCL_CLIENT_SECRET"]
        self._token = None
        self._expires = 0
        self.session = requests.Session()

    def _auth(self):
        if self._token and time.time() < self._expires - 60:
            return self._token
        r = self.session.post(TOKEN_URL, data={"grant_type": "client_credentials"},
                              auth=(self._id, self._secret), timeout=30)
        r.raise_for_status()
        j = r.json()
        self._token = j["access_token"]
        self._expires = time.time() + j["expires_in"]
        return self._token

    def query(self, q, variables=None, retries=3):
        for attempt in range(retries):
            r = self.session.post(API_URL, json={"query": q, "variables": variables or {}},
                                  headers={"Authorization": f"Bearer {self._auth()}"}, timeout=60)
            if r.status_code == 429 and attempt < retries - 1:
                time.sleep(2 ** (attempt + 2))
                continue
            r.raise_for_status()
            j = r.json()
            if j.get("errors"):
                raise RuntimeError(j["errors"])
            return j["data"]

    def rate_limit(self):
        return self.query("{ rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn } }")["rateLimitData"]

    def events(self, code, fight_id, source_id=None, data_type="All", include_resources=False,
               start=None, end=None, **extra):
        """Yield all events for one fight, following nextPageTimestamp pagination."""
        q = """query($c:String!,$f:[Int]!,$s:Int,$t:EventDataType,$st:Float,$en:Float,$r:Boolean,$hostility:HostilityType,$filter:String){
          reportData{ report(code:$c){ events(fightIDs:$f, sourceID:$s, dataType:$t, startTime:$st, endTime:$en,
            includeResources:$r, hostilityType:$hostility, filterExpression:$filter, limit:10000){ data nextPageTimestamp } } } }"""
        if start is None or end is None:
            f = self.fight(code, fight_id)
            start, end = f["startTime"], f["endTime"]
        while start is not None:
            v = {"c": code, "f": [fight_id], "s": source_id, "t": data_type, "st": start, "en": end,
                 "r": include_resources, "hostility": extra.get("hostility"), "filter": extra.get("filter")}
            page = self.query(q, v)["reportData"]["report"]["events"]
            yield from page["data"]
            start = page["nextPageTimestamp"]

    def fight(self, code, fight_id):
        q = """query($c:String!,$f:[Int]!){ reportData{ report(code:$c){ fights(fightIDs:$f){
          id encounterID name difficulty kill startTime endTime keystoneLevel keystoneTime } } } }"""
        return self.query(q, {"c": code, "f": [fight_id]})["reportData"]["report"]["fights"][0]

    def abilities(self, code):
        q = """query($c:String!){ reportData{ report(code:$c){ masterData{ abilities{ gameID name type } } } } }"""
        return {a["gameID"]: a["name"] for a in self.query(q, {"c": code})["reportData"]["report"]["masterData"]["abilities"]}

    def player_details(self, code, fight_id):
        q = """query($c:String!,$f:[Int]!){ reportData{ report(code:$c){
          playerDetails(fightIDs:$f, includeCombatantInfo:true) } } }"""
        return self.query(q, {"c": code, "f": [fight_id]})["reportData"]["report"]["playerDetails"]["data"]["playerDetails"]

    def top_havoc(self, encounter_id, difficulty=None, page=1, metric="dps"):
        q = """query($e:Int!,$d:Int,$p:Int,$m:CharacterRankingMetricType){ worldData{ encounter(id:$e){
          characterRankings(className:"DemonHunter", specName:"Havoc", difficulty:$d, page:$p, metric:$m) } } }"""
        return self.query(q, {"e": encounter_id, "d": difficulty, "p": page, "m": metric})["worldData"]["encounter"]["characterRankings"]
