import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.misc.api.models.companies.index import Empresa
from apps.users.api.models.index import User, UserCompanyProfile


class BootstrapGlobalOilEtlAccountsTests(TestCase):
    @patch.dict(os.environ, {"ETL_BOOTSTRAP_PASSWORD": "Bootstrap-password-123!"})
    def test_creates_idempotent_access_baseline(self):
        call_command("bootstrap_globaloil_etl_accounts", "--reset-passwords", stdout=StringIO())
        call_command("bootstrap_globaloil_etl_accounts", stdout=StringIO())

        self.assertEqual(Empresa.objects.filter(nombre="Global Oil").count(), 1)
        self.assertEqual(Empresa.objects.filter(nombre="MINEROS ALUVIAL S.A.S.").count(), 1)
        self.assertEqual(User.objects.filter(email__in=[
            "admin@globaloil.local",
            "laboratorista@globaloil.local",
            "admin@minerosaluvial.local",
            "muestras@minerosaluvial.local",
        ]).count(), 4)
        global_admin = User.objects.get(email="admin@globaloil.local")
        self.assertTrue(global_admin.is_superuser)
        self.assertTrue(global_admin.check_password("Bootstrap-password-123!"))
        self.assertTrue(global_admin.empresa.is_internal)
        self.assertEqual(
            UserCompanyProfile.objects.get(user=global_admin).role.code,
            "admin_global",
        )
        mineros = Empresa.objects.get(nombre="MINEROS ALUVIAL S.A.S.")
        self.assertFalse(mineros.is_internal)
        self.assertEqual(
            set(UserCompanyProfile.objects.filter(empresa=mineros).values_list("role__code", flat=True)),
            {"admin_empresa", "empresa_carga_muestras"},
        )
        self.assertEqual(
            UserCompanyProfile.objects.filter(empresa=mineros, is_company_admin=True).count(),
            1,
        )
