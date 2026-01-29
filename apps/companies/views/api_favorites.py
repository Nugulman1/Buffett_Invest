"""
기업 API: 즐겨찾기
"""
from django.db.models import Prefetch
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from apps.service.corp_code import resolve_corp_code


def _get_favorite_models():
    """즐겨찾기 관련 모델 (FavoriteGroup, Favorite, Company) 반환."""
    from django.apps import apps as django_apps

    return (
        django_apps.get_model("apps", "FavoriteGroup"),
        django_apps.get_model("apps", "Favorite"),
        django_apps.get_model("apps", "Company"),
    )


@api_view(["GET"])
def get_favorites(request):
    """
    즐겨찾기 목록 조회 API
    GET /api/companies/favorites/
    """
    try:
        FavoriteGroupModel, FavoriteModel, _ = _get_favorite_models()
        groups = FavoriteGroupModel.objects.prefetch_related(
            Prefetch(
                "favorites",
                queryset=FavoriteModel.objects.select_related("company").order_by(
                    "company__company_name"
                ),
            )
        ).order_by("name")
        result = []
        for group in groups:
            favorites = group.favorites.all()
            result.append({
                "group_id": group.id,
                "group_name": group.name,
                "favorites": [
                    {
                        "id": fav.id,
                        "corp_code": fav.company.corp_code,
                        "company_name": fav.company.company_name or "",
                        "created_at": (
                            fav.created_at.isoformat() if fav.created_at else None
                        ),
                    }
                    for fav in favorites
                ],
            })
        return Response({"groups": result}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST", "DELETE"])
def favorite(request, corp_code):
    """
    즐겨찾기 추가 및 삭제 API
    POST /api/companies/<corp_code>/favorites/ - 추가
    DELETE /api/companies/<corp_code>/favorites/ - 삭제
    """
    try:
        FavoriteGroupModel, FavoriteModel, CompanyModel = _get_favorite_models()
        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            return Response(
                {"error": f"기업코드 {corp_code}에 해당하는 기업을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == "POST":
            group_id = request.data.get("group_id")
            if not group_id:
                return Response(
                    {"error": "group_id가 필요합니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                group_id = int(group_id)
            except (ValueError, TypeError):
                return Response(
                    {"error": "group_id는 정수여야 합니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                group = FavoriteGroupModel.objects.get(id=group_id)
            except FavoriteGroupModel.DoesNotExist:
                return Response(
                    {"error": f"그룹 ID {group_id}를 찾을 수 없습니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            fav, created = FavoriteModel.objects.get_or_create(
                group=group,
                company=company,
                defaults={},
            )
            if not created:
                return Response(
                    {"error": "이미 즐겨찾기에 추가된 기업입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    "id": fav.id,
                    "corp_code": company.corp_code,
                    "company_name": company.company_name or "",
                    "group_id": group.id,
                    "group_name": group.name,
                    "created_at": (
                        fav.created_at.isoformat() if fav.created_at else None
                    ),
                },
                status=status.HTTP_201_CREATED,
            )
        elif request.method == "DELETE":
            deleted_count, _ = FavoriteModel.objects.filter(
                company=company
            ).delete()
            if deleted_count == 0:
                return Response(
                    {"error": "즐겨찾기에 없는 기업입니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(
                {"corp_code": corp_code, "deleted_count": deleted_count},
                status=status.HTTP_200_OK,
            )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["DELETE"])
def favorite_detail(request, favorite_id):
    """
    즐겨찾기 삭제 API (특정 그룹에서만)
    DELETE /api/companies/favorites/<favorite_id>/
    """
    try:
        _, FavoriteModel, _ = _get_favorite_models()
        try:
            favorite_id = int(favorite_id)
        except (ValueError, TypeError):
            return Response(
                {"error": f"유효하지 않은 즐겨찾기 ID입니다: {favorite_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            favorite = FavoriteModel.objects.get(id=favorite_id)
        except FavoriteModel.DoesNotExist:
            return Response(
                {"error": f"즐겨찾기 ID {favorite_id}를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        corp_code = favorite.company.corp_code
        company_name = favorite.company.company_name or ""
        group_name = favorite.group.name
        favorite.delete()
        return Response(
            {
                "id": favorite_id,
                "corp_code": corp_code,
                "company_name": company_name,
                "group_name": group_name,
                "message": "즐겨찾기에서 삭제되었습니다.",
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["PUT"])
def change_favorite_group(request, favorite_id):
    """
    즐겨찾기 그룹 변경 API
    PUT /api/companies/favorites/<favorite_id>/group/
    Body: {"group_id": 2}
    """
    try:
        FavoriteGroupModel, FavoriteModel, _ = _get_favorite_models()
        try:
            favorite = FavoriteModel.objects.get(id=favorite_id)
        except FavoriteModel.DoesNotExist:
            return Response(
                {"error": f"즐겨찾기 ID {favorite_id}를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        group_id = request.data.get("group_id")
        if not group_id:
            return Response(
                {"error": "group_id가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            group_id = int(group_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "group_id는 정수여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            group = FavoriteGroupModel.objects.get(id=group_id)
        except FavoriteGroupModel.DoesNotExist:
            return Response(
                {"error": f"그룹 ID {group_id}를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if favorite.group.id == group_id:
            return Response(
                {
                    "id": favorite.id,
                    "corp_code": favorite.company.corp_code,
                    "company_name": favorite.company.company_name or "",
                    "group_id": group.id,
                    "group_name": group.name,
                },
                status=status.HTTP_200_OK,
            )
        if FavoriteModel.objects.filter(
            group=group, company=favorite.company
        ).exists():
            return Response(
                {"error": "해당 그룹에 이미 같은 기업이 있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        favorite.group = group
        favorite.save()
        return Response(
            {
                "id": favorite.id,
                "corp_code": favorite.company.corp_code,
                "company_name": favorite.company.company_name or "",
                "group_id": group.id,
                "group_name": group.name,
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET", "POST"])
def favorite_groups(request):
    """
    즐겨찾기 그룹 목록 조회 및 생성 API
    GET /api/companies/favorite-groups/
    POST /api/companies/favorite-groups/
    """
    try:
        FavoriteGroupModel, _, _ = _get_favorite_models()
        if request.method == "GET":
            groups = FavoriteGroupModel.objects.all().order_by("name")
            return Response(
                {
                    "groups": [
                        {
                            "id": g.id,
                            "name": g.name,
                            "created_at": (
                                g.created_at.isoformat() if g.created_at else None
                            ),
                        }
                        for g in groups
                    ]
                },
                status=status.HTTP_200_OK,
            )
        elif request.method == "POST":
            name = request.data.get("name", "").strip()
            if not name:
                return Response(
                    {"error": "그룹명이 필요합니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if FavoriteGroupModel.objects.filter(name=name).exists():
                return Response(
                    {"error": "이미 같은 이름의 그룹이 있습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            group = FavoriteGroupModel.objects.create(name=name)
            return Response(
                {
                    "id": group.id,
                    "name": group.name,
                    "created_at": (
                        group.created_at.isoformat() if group.created_at else None
                    ),
                },
                status=status.HTTP_201_CREATED,
            )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["PUT", "DELETE"])
def favorite_group_detail(request, group_id):
    """
    즐겨찾기 그룹 수정 및 삭제 API
    PUT /api/companies/favorite-groups/<group_id>/
    DELETE /api/companies/favorite-groups/<group_id>/
    """
    try:
        FavoriteGroupModel, _, _ = _get_favorite_models()
        try:
            group = FavoriteGroupModel.objects.get(id=group_id)
        except FavoriteGroupModel.DoesNotExist:
            return Response(
                {"error": f"그룹 ID {group_id}를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if request.method == "PUT":
            name = request.data.get("name", "").strip()
            if not name:
                return Response(
                    {"error": "그룹명이 필요합니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if (
                FavoriteGroupModel.objects.filter(name=name)
                .exclude(id=group_id)
                .exists()
            ):
                return Response(
                    {"error": "이미 같은 이름의 그룹이 있습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            group.name = name
            group.save()
            return Response(
                {
                    "id": group.id,
                    "name": group.name,
                    "created_at": (
                        group.created_at.isoformat() if group.created_at else None
                    ),
                    "updated_at": (
                        group.updated_at.isoformat() if group.updated_at else None
                    ),
                },
                status=status.HTTP_200_OK,
            )
        elif request.method == "DELETE":
            group_name = group.name
            group.delete()
            return Response(
                {
                    "id": group_id,
                    "name": group_name,
                    "message": "그룹이 삭제되었습니다.",
                },
                status=status.HTTP_200_OK,
            )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
