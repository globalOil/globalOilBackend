"""Create the minimum access baseline required before the Global Oil ETL."""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.misc.api.models.companies.index import Empresa
from apps.users.api.models.index import SecurityRole, User, UserCompanyProfile
from apps.users.api.services import ensure_user_profile, seed_default_permissions


GLOBAL_COMPANY = ("Global Oil", "GLOBAL-OIL-INTERNAL", True)
MINEROS_COMPANY = ("MINEROS ALUVIAL S.A.S.", "MINEROS-ALUVIAL", False)
ACCOUNTS = (
    ("admin@globaloil.local", "Administrador", "Global", User.Role.GLOBAL, "admin_global", "Global Oil", True, True, True),
    ("laboratorista@globaloil.local", "Laboratorista", "Global Oil", User.Role.LABORATORISTA, "laboratorista", "Global Oil", False, False, False),
    ("admin@minerosaluvial.local", "Administrador", "Mineros Aluvial", User.Role.ADMIN, "admin_empresa", "MINEROS ALUVIAL S.A.S.", True, False, False),
    ("muestras@minerosaluvial.local", "Carga de", "Muestras", User.Role.EMPRESA, "empresa_carga_muestras", "MINEROS ALUVIAL S.A.S.", False, False, False),
)


class Command(BaseCommand):
    help = (
        "Crea o actualiza las cuatro cuentas iniciales de la ETL: administrador "
        "Global Oil, laboratorista, administrador Mineros y carga de muestras Mineros."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password-env",
            default="ETL_BOOTSTRAP_PASSWORD",
            help="Variable de entorno con la contraseña inicial (nunca se imprime).",
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Actualiza la contraseña de las cuentas existentes con la variable indicada.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.environ.get(options["password_env"], "")
        if len(password) < 12:
            raise CommandError(
                f"Defina {options['password_env']} con una contraseña de al menos 12 caracteres."
            )

        seed_default_permissions()
        companies = {}
        for name, nit, is_internal in (GLOBAL_COMPANY, MINEROS_COMPANY):
            company, _ = Empresa.objects.update_or_create(
                nombre=name,
                defaults={
                    "nit": nit,
                    "email": "contacto@globaloil.local" if is_internal else "contacto@minerosaluvial.local",
                    "is_active": True,
                    "is_internal": is_internal,
                    "status": Empresa.Status.ACTIVE,
                },
            )
            companies[name] = company

        for email, first_name, last_name, legacy_role, role_code, company_name, is_company_admin, is_staff, is_superuser in ACCOUNTS:
            company = companies[company_name]
            user, created = User.objects.update_or_create(
                email=email,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": legacy_role,
                    "empresa": company,
                    "is_active": True,
                    "email_verified": True,
                    "access_status": User.AccessStatus.ACTIVE,
                    "is_read_only": False,
                    "is_staff": is_staff,
                    "is_superuser": is_superuser,
                    "home_path": "",
                    "data_scope_override": "",
                },
            )
            if created or options["reset_passwords"]:
                user.set_password(password)
                user.save(update_fields=["password"])

            role = SecurityRole.objects.get(code=role_code, active=True)
            ensure_user_profile(
                user,
                company,
                role=role,
                is_company_admin=is_company_admin,
                status=UserCompanyProfile.Status.ACTIVE,
            )
            self.stdout.write(f"{email} [{role.code}]")

        self.stdout.write(self.style.SUCCESS("Accesos iniciales de Global Oil y Mineros Aluvial listos."))
