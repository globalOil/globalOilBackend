"""Make imported local accounts reproducible after an ETL security reset."""

import json
import os
import re
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.misc.api.models.companies.index import Empresa
from apps.users.api.models.index import SecurityRole, User, UserCompanyProfile
from apps.users.api.services import ensure_user_profile


def _key(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _company_key_from_email(email):
    return _key(str(email or "").split("@")[-1].split(".")[0])


def _role_for_company_user(user):
    if user.role == User.Role.ADMIN:
        return "admin_empresa", True
    local_part = str(user.email or "").split("@", 1)[0].casefold()
    if "muestra" in local_part or "carga" in local_part:
        return "empresa_carga_muestras", False
    return "empresa_consulta", False


class Command(BaseCommand):
    help = (
        "Restablece la clave indicada para todas las cuentas activas del entorno local "
        "y reatacha cuentas de empresa identificables por su dominio."
    )

    def add_arguments(self, parser):
        parser.add_argument("--password-env", default="ETL_ACCOUNT_PASSWORD")
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.environ.get(options["password_env"], "")
        if len(password) < 12:
            raise CommandError(
                f"Defina {options['password_env']} con al menos 12 caracteres; no se guarda ninguna clave en el repositorio."
            )

        companies = list(Empresa.objects.filter(is_active=True, is_internal=False).order_by("id"))
        roles = {
            role.code: role
            for role in SecurityRole.objects.filter(
                code__in=("admin_empresa", "empresa_carga_muestras", "empresa_consulta"),
                active=True,
            )
        }
        summary = {"passwords_reset": [], "company_profiles_restored": [], "unmatched_active_accounts": []}

        for user in User.objects.filter(is_active=True).order_by("id"):
            summary["passwords_reset"].append(user.email)
            original_company_id = user.empresa_id
            if not options["dry_run"]:
                user.set_password(password)

            # A Global account is intentionally not attached to a customer.
            if user.role == User.Role.GLOBAL or user.is_superuser:
                if not options["dry_run"]:
                    user.save(update_fields=["password"])
                continue

            company = user.empresa
            if not company:
                domain_key = _company_key_from_email(user.email)
                matches = [item for item in companies if domain_key and _key(item.nombre).startswith(domain_key)]
                if len(matches) == 1:
                    company = matches[0]
                    user.empresa = company
                else:
                    summary["unmatched_active_accounts"].append(user.email)

            if not options["dry_run"]:
                fields = ["password"]
                if company and original_company_id != company.id:
                    fields.append("empresa")
                user.save(update_fields=fields)

            if not company:
                continue
            role_code, is_company_admin = _role_for_company_user(user)
            role = roles.get(role_code)
            if not role:
                continue
            summary["company_profiles_restored"].append({"email": user.email, "empresa": company.nombre, "rol": role_code})
            if options["dry_run"]:
                continue
            profile = ensure_user_profile(
                user,
                company,
                role=role,
                is_company_admin=is_company_admin,
                status=UserCompanyProfile.Status.ACTIVE,
            )
            if not profile.activated_at:
                profile.activated_at = timezone.now()
                profile.save(update_fields=["activated_at", "updated_at"])

        self.stdout.write(json.dumps({
            "mode": "dry_run" if options["dry_run"] else "apply",
            **summary,
        }, ensure_ascii=False))
