"""
즐겨찾기 API 6개 뷰 characterization 테스트 (회귀 안전망).

목적: apps/companies/views/api_favorites.py 의 현재 HTTP 동작을 그대로 박제한다.
곧 뷰의 DB 접근 로직을 db.py로 이관하는 리팩터를 할 예정이며, 이 테스트는
리팩터 전후 응답(status_code + body 핵심 필드) 동등성을 보장한다.

기대값은 RED가 아니라 현재 코드 동작에서 도출 — 현재 코드로 전부 GREEN이어야 한다.

URL 경로는 config/urls.py 의 api/companies/ include 에서 확인:
- GET    /api/companies/favorites/
- POST   /api/companies/<corp_code>/favorites/
- DELETE /api/companies/<corp_code>/favorites/
- DELETE /api/companies/favorites/<int:favorite_id>/
- PUT    /api/companies/favorites/<int:favorite_id>/group/
- GET    /api/companies/favorite-groups/
- POST   /api/companies/favorite-groups/
- PUT    /api/companies/favorite-groups/<int:group_id>/
- DELETE /api/companies/favorite-groups/<int:group_id>/

corp_code는 8자리를 사용한다 — resolve_corp_code()는 6자리 종목코드만 DART로
변환하고 8자리는 그대로 통과시키므로(apps/service/corp_code.py), 외부 API 호출 없이
DB만으로 동작을 검증할 수 있다.
"""
import pytest
from rest_framework.test import APIClient

from apps.models import Company, FavoriteGroup, Favorite


@pytest.fixture
def client():
    return APIClient()


def _make_company(corp_code="00000001", name="테스트기업"):
    return Company.objects.create(corp_code=corp_code, company_name=name)


def _make_group(name="내그룹"):
    return FavoriteGroup.objects.create(name=name)


# ── GET /api/companies/favorites/  (get_favorites) ─────────────────────────
@pytest.mark.django_db
class TestGetFavorites:
    def test_empty(self, client):
        """즐겨찾기가 하나도 없으면 groups=[] 반환, 200."""
        resp = client.get("/api/companies/favorites/")
        assert resp.status_code == 200
        assert resp.json() == {"groups": []}

    def test_groups_ordered_by_name_with_favorites(self, client):
        """그룹은 name 오름차순, 각 그룹에 소속 즐겨찾기(corp_code/company_name/created_at) 포함."""
        g_b = _make_group("B그룹")
        g_a = _make_group("A그룹")
        c = _make_company("00000001", "삼성전자")
        fav = Favorite.objects.create(group=g_a, company=c)

        resp = client.get("/api/companies/favorites/")
        assert resp.status_code == 200
        body = resp.json()
        # name 오름차순 → A그룹 먼저
        assert [g["group_name"] for g in body["groups"]] == ["A그룹", "B그룹"]
        a = body["groups"][0]
        assert a["group_id"] == g_a.id
        assert a["favorites"][0]["id"] == fav.id
        assert a["favorites"][0]["corp_code"] == "00000001"
        assert a["favorites"][0]["company_name"] == "삼성전자"
        assert a["favorites"][0]["created_at"] is not None
        # 빈 그룹은 favorites=[]
        assert body["groups"][1]["group_id"] == g_b.id
        assert body["groups"][1]["favorites"] == []


# ── GET/POST /api/companies/favorite-groups/  (favorite_groups) ────────────
@pytest.mark.django_db
class TestFavoriteGroupsListCreate:
    def test_list_ordered_by_name(self, client):
        _make_group("나그룹")
        _make_group("가그룹")
        resp = client.get("/api/companies/favorite-groups/")
        assert resp.status_code == 200
        names = [g["name"] for g in resp.json()["groups"]]
        assert names == ["가그룹", "나그룹"]
        # 각 항목 핵심 필드
        first = resp.json()["groups"][0]
        assert set(first.keys()) == {"id", "name", "created_at"}
        assert first["created_at"] is not None

    def test_create_success(self, client):
        resp = client.post(
            "/api/companies/favorite-groups/", {"name": "새그룹"}, format="json"
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "새그룹"
        assert body["created_at"] is not None
        assert FavoriteGroup.objects.filter(name="새그룹").exists()

    def test_create_strips_whitespace(self, client):
        """이름 앞뒤 공백은 strip 되어 저장된다 (현재 동작)."""
        resp = client.post(
            "/api/companies/favorite-groups/", {"name": "  공백그룹  "}, format="json"
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "공백그룹"

    def test_create_empty_name_400(self, client):
        resp = client.post(
            "/api/companies/favorite-groups/", {"name": "   "}, format="json"
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "그룹명이 필요합니다."

    def test_create_missing_name_400(self, client):
        resp = client.post("/api/companies/favorite-groups/", {}, format="json")
        assert resp.status_code == 400
        assert resp.json()["error"] == "그룹명이 필요합니다."

    def test_create_duplicate_name_400(self, client):
        _make_group("중복")
        resp = client.post(
            "/api/companies/favorite-groups/", {"name": "중복"}, format="json"
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "이미 같은 이름의 그룹이 있습니다."


# ── PUT/DELETE /api/companies/favorite-groups/<id>/  (favorite_group_detail)
@pytest.mark.django_db
class TestFavoriteGroupDetail:
    def test_rename_success(self, client):
        g = _make_group("원래이름")
        resp = client.put(
            f"/api/companies/favorite-groups/{g.id}/",
            {"name": "바뀐이름"},
            format="json",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == g.id
        assert body["name"] == "바뀐이름"
        # PUT 응답에만 updated_at 포함 (현재 동작)
        assert "updated_at" in body
        assert body["updated_at"] is not None
        g.refresh_from_db()
        assert g.name == "바뀐이름"

    def test_rename_empty_400(self, client):
        g = _make_group()
        resp = client.put(
            f"/api/companies/favorite-groups/{g.id}/", {"name": "  "}, format="json"
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "그룹명이 필요합니다."

    def test_rename_duplicate_400(self, client):
        _make_group("이미있음")
        g = _make_group("나")
        resp = client.put(
            f"/api/companies/favorite-groups/{g.id}/",
            {"name": "이미있음"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "이미 같은 이름의 그룹이 있습니다."

    def test_rename_to_own_name_ok(self, client):
        """자기 자신과 같은 이름으로 수정은 exclude(id) 덕분에 허용된다 (현재 동작)."""
        g = _make_group("자기이름")
        resp = client.put(
            f"/api/companies/favorite-groups/{g.id}/",
            {"name": "자기이름"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "자기이름"

    def test_rename_nonexistent_404(self, client):
        resp = client.put(
            "/api/companies/favorite-groups/999999/", {"name": "x"}, format="json"
        )
        assert resp.status_code == 404
        assert "999999" in resp.json()["error"]

    def test_delete_success_cascades(self, client):
        g = _make_group("삭제될그룹")
        c = _make_company()
        Favorite.objects.create(group=g, company=c)
        resp = client.delete(f"/api/companies/favorite-groups/{g.id}/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == g.id
        assert body["name"] == "삭제될그룹"
        assert body["message"] == "그룹이 삭제되었습니다."
        assert not FavoriteGroup.objects.filter(id=g.id).exists()
        # FK cascade로 소속 즐겨찾기도 삭제
        assert Favorite.objects.count() == 0

    def test_delete_nonexistent_404(self, client):
        resp = client.delete("/api/companies/favorite-groups/999999/")
        assert resp.status_code == 404
        assert "999999" in resp.json()["error"]


# ── POST/DELETE /api/companies/<corp_code>/favorites/  (favorite) ──────────
@pytest.mark.django_db
class TestFavoriteAddDelete:
    def test_add_success(self, client):
        g = _make_group()
        _make_company("00000001", "삼성전자")
        resp = client.post(
            "/api/companies/00000001/favorites/",
            {"group_id": g.id},
            format="json",
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["corp_code"] == "00000001"
        assert body["company_name"] == "삼성전자"
        assert body["group_id"] == g.id
        assert body["group_name"] == g.name
        assert body["created_at"] is not None
        assert Favorite.objects.filter(company_id="00000001", group=g).exists()

    def test_add_duplicate_400(self, client):
        """get_or_create로 이미 존재하면 created=False → 400."""
        g = _make_group()
        c = _make_company()
        Favorite.objects.create(group=g, company=c)
        resp = client.post(
            "/api/companies/00000001/favorites/",
            {"group_id": g.id},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "이미 즐겨찾기에 추가된 기업입니다."

    def test_add_missing_group_id_400(self, client):
        _make_company()
        resp = client.post("/api/companies/00000001/favorites/", {}, format="json")
        assert resp.status_code == 400
        assert resp.json()["error"] == "group_id가 필요합니다."

    def test_add_non_int_group_id_400(self, client):
        _make_company()
        resp = client.post(
            "/api/companies/00000001/favorites/",
            {"group_id": "abc"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "group_id는 정수여야 합니다."

    def test_add_nonexistent_group_404(self, client):
        _make_company()
        resp = client.post(
            "/api/companies/00000001/favorites/",
            {"group_id": 999999},
            format="json",
        )
        assert resp.status_code == 404
        assert "999999" in resp.json()["error"]

    def test_add_nonexistent_corp_404(self, client):
        """존재하지 않는 8자리 corp_code → resolve는 통과, Company 조회 실패 404."""
        g = _make_group()
        resp = client.post(
            "/api/companies/00009999/favorites/",
            {"group_id": g.id},
            format="json",
        )
        assert resp.status_code == 404
        assert "00009999" in resp.json()["error"]

    def test_delete_success(self, client):
        """corp_code 기준 삭제 — 해당 기업의 모든 즐겨찾기 삭제, deleted_count 반환."""
        g1 = _make_group("그룹1")
        g2 = _make_group("그룹2")
        c = _make_company()
        Favorite.objects.create(group=g1, company=c)
        Favorite.objects.create(group=g2, company=c)
        resp = client.delete("/api/companies/00000001/favorites/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["corp_code"] == "00000001"
        assert body["deleted_count"] == 2
        assert Favorite.objects.filter(company=c).count() == 0

    def test_delete_not_favorited_404(self, client):
        """기업은 존재하나 즐겨찾기에 없으면 deleted_count=0 → 404."""
        _make_company()
        resp = client.delete("/api/companies/00000001/favorites/")
        assert resp.status_code == 404
        assert resp.json()["error"] == "즐겨찾기에 없는 기업입니다."

    def test_delete_nonexistent_corp_404(self, client):
        resp = client.delete("/api/companies/00009999/favorites/")
        assert resp.status_code == 404
        assert "00009999" in resp.json()["error"]


# ── PUT /api/companies/favorites/<id>/group/  (change_favorite_group) ──────
@pytest.mark.django_db
class TestChangeFavoriteGroup:
    def test_move_success(self, client):
        g1 = _make_group("출발그룹")
        g2 = _make_group("도착그룹")
        c = _make_company("00000001", "삼성전자")
        fav = Favorite.objects.create(group=g1, company=c)
        resp = client.put(
            f"/api/companies/favorites/{fav.id}/group/",
            {"group_id": g2.id},
            format="json",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == fav.id
        assert body["corp_code"] == "00000001"
        assert body["company_name"] == "삼성전자"
        assert body["group_id"] == g2.id
        assert body["group_name"] == "도착그룹"
        fav.refresh_from_db()
        assert fav.group_id == g2.id

    def test_move_to_same_group_returns_current_200(self, client):
        """같은 그룹으로 변경 요청 → 변경 없이 현재 상태 200 반환."""
        g1 = _make_group("그룹1")
        c = _make_company()
        fav = Favorite.objects.create(group=g1, company=c)
        resp = client.put(
            f"/api/companies/favorites/{fav.id}/group/",
            {"group_id": g1.id},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["group_id"] == g1.id

    def test_move_duplicate_in_target_400(self, client):
        """대상 그룹에 같은 기업이 이미 있으면 400."""
        g1 = _make_group("그룹1")
        g2 = _make_group("그룹2")
        c = _make_company()
        fav = Favorite.objects.create(group=g1, company=c)
        Favorite.objects.create(group=g2, company=c)  # g2에도 이미 존재
        resp = client.put(
            f"/api/companies/favorites/{fav.id}/group/",
            {"group_id": g2.id},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "해당 그룹에 이미 같은 기업이 있습니다."

    def test_nonexistent_favorite_404(self, client):
        g = _make_group()
        resp = client.put(
            "/api/companies/favorites/999999/group/",
            {"group_id": g.id},
            format="json",
        )
        assert resp.status_code == 404
        assert "999999" in resp.json()["error"]

    def test_missing_group_id_400(self, client):
        c = _make_company()
        g = _make_group()
        fav = Favorite.objects.create(group=g, company=c)
        resp = client.put(
            f"/api/companies/favorites/{fav.id}/group/", {}, format="json"
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "group_id가 필요합니다."

    def test_non_int_group_id_400(self, client):
        c = _make_company()
        g = _make_group()
        fav = Favorite.objects.create(group=g, company=c)
        resp = client.put(
            f"/api/companies/favorites/{fav.id}/group/",
            {"group_id": "abc"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "group_id는 정수여야 합니다."

    def test_nonexistent_target_group_404(self, client):
        c = _make_company()
        g = _make_group()
        fav = Favorite.objects.create(group=g, company=c)
        resp = client.put(
            f"/api/companies/favorites/{fav.id}/group/",
            {"group_id": 999999},
            format="json",
        )
        assert resp.status_code == 404
        assert "999999" in resp.json()["error"]


# ── DELETE /api/companies/favorites/<id>/  (favorite_detail) ───────────────
@pytest.mark.django_db
class TestFavoriteDetail:
    def test_delete_success(self, client):
        g = _make_group("내그룹")
        c = _make_company("00000001", "삼성전자")
        fav = Favorite.objects.create(group=g, company=c)
        resp = client.delete(f"/api/companies/favorites/{fav.id}/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == fav.id
        assert body["corp_code"] == "00000001"
        assert body["company_name"] == "삼성전자"
        assert body["group_name"] == "내그룹"
        assert body["message"] == "즐겨찾기에서 삭제되었습니다."
        assert not Favorite.objects.filter(id=fav.id).exists()

    def test_delete_nonexistent_404(self, client):
        resp = client.delete("/api/companies/favorites/999999/")
        assert resp.status_code == 404
        assert "999999" in resp.json()["error"]

    def test_non_int_id_resolves_to_404(self, client):
        """URL이 <int:favorite_id>라 비정수 경로는 라우팅 단계에서 404.
        뷰 내부의 int() 변환 400 분기는 HTTP로는 도달 불가 — 실제 동작은 404."""
        resp = client.delete("/api/companies/favorites/abc/")
        assert resp.status_code == 404
