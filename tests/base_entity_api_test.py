from typing import Any, Dict

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class BaseEntityApiTest:
    __test__ = False

    endpoint: str = ""
    create_payload: Dict[str, Any] = {}
    update_payload: Dict[str, Any] = {}
    invalid_payload: Dict[str, Any] = {}
    filter_field: str = ""
    filter_value: Any = None
    other_filter_value: Any = None

    allow_create: bool = True
    allow_update: bool = True
    allow_delete: bool = True
    method_not_allowed_status: int = 405

    def make_model(self, index: int, **overrides):
        raise NotImplementedError

    def build_create_payload(self) -> Dict[str, Any]:
        return self.create_payload

    def build_update_payload(self, row) -> Dict[str, Any]:
        return self.update_payload

    @pytest.mark.asyncio
    async def test_create(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        auth_headers_admin: Dict[str, str],
    ):
        payload = self.build_create_payload()
        response = await client.post(
            self.endpoint,
            json=payload,
            headers=auth_headers_admin,
        )

        if not self.allow_create:
            assert response.status_code == self.method_not_allowed_status, response.text
            return

        assert response.status_code == 200, response.text
        data = response.json()
        for key, value in payload.items():
            assert data[key] == value
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_list(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        auth_headers_user: Dict[str, str],
    ):
        first = self.make_model(1)
        second = self.make_model(2)
        test_db.add_all([first, second])
        await test_db.commit()

        response = await client.get(self.endpoint, headers=auth_headers_user)

        assert response.status_code == 200, response.text
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        assert len(data["data"]) >= 2
        assert data["pagination"]["total_records"] >= 2

    @pytest.mark.asyncio
    async def test_list_with_filtering(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        auth_headers_user: Dict[str, str],
    ):
        one = self.make_model(1, **{self.filter_field: self.filter_value})
        two = self.make_model(2, **{self.filter_field: self.other_filter_value})
        test_db.add_all([one, two])
        await test_db.commit()

        response = await client.get(
            f"{self.endpoint}?{self.filter_field}={self.filter_value}",
            headers=auth_headers_user,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data["data"]) >= 1
        assert any(
            item[self.filter_field] == self.filter_value for item in data["data"]
        )

    @pytest.mark.asyncio
    async def test_list_with_search(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        auth_headers_user: Dict[str, str],
    ):
        one = self.make_model(1, **{self.filter_field: self.filter_value})
        two = self.make_model(2, **{self.filter_field: self.other_filter_value})
        test_db.add_all([one, two])
        await test_db.commit()

        response = await client.get(
            f"{self.endpoint}?search=%{self.filter_value}%",
            headers=auth_headers_user,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data["data"]) >= 1
        assert any(
            self.filter_value.lower() in str(item).lower() for item in data["data"]
        )

    @pytest.mark.asyncio
    async def test_get(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        auth_headers_user: Dict[str, str],
    ):
        row = self.make_model(1)
        test_db.add(row)
        await test_db.commit()
        await test_db.refresh(row)

        response = await client.get(
            f"{self.endpoint}{row.id}", headers=auth_headers_user
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["id"] == row.id

    @pytest.mark.asyncio
    async def test_get_not_found(
        self,
        client: AsyncClient,
        auth_headers_user: Dict[str, str],
    ):
        response = await client.get(f"{self.endpoint}99999", headers=auth_headers_user)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        auth_headers_admin: Dict[str, str],
    ):
        row = self.make_model(1)
        test_db.add(row)
        await test_db.commit()
        await test_db.refresh(row)

        payload = self.build_update_payload(row)
        response = await client.patch(
            f"{self.endpoint}{row.id}",
            json=payload,
            headers=auth_headers_admin,
        )

        if not self.allow_update:
            assert response.status_code == self.method_not_allowed_status, response.text
            return

        assert response.status_code == 200, response.text
        data = response.json()
        for key, value in payload.items():
            assert data[key] == value

    @pytest.mark.asyncio
    async def test_delete(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        auth_headers_admin: Dict[str, str],
    ):
        row = self.make_model(1)
        test_db.add(row)
        await test_db.commit()
        await test_db.refresh(row)

        response = await client.delete(
            f"{self.endpoint}{row.id}", headers=auth_headers_admin
        )

        if not self.allow_delete:
            assert response.status_code == self.method_not_allowed_status, response.text
            return

        assert response.status_code == 204

        verify = await client.get(
            f"{self.endpoint}{row.id}", headers=auth_headers_admin
        )
        assert verify.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(
        self,
        client: AsyncClient,
        auth_headers_admin: Dict[str, str],
    ):
        response = await client.delete(
            f"{self.endpoint}99999", headers=auth_headers_admin
        )

        if not self.allow_delete:
            assert response.status_code == self.method_not_allowed_status, response.text
            return

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_validation_error(
        self,
        client: AsyncClient,
        auth_headers_admin: Dict[str, str],
    ):
        response = await client.post(
            self.endpoint,
            json=self.invalid_payload,
            headers=auth_headers_admin,
        )

        if not self.allow_create:
            assert response.status_code in [
                self.method_not_allowed_status,
                422,
            ], response.text
            return

        assert response.status_code in [400, 422]
