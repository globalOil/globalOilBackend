"""Restore company-admin memberships after a clean historical import.

The security reset preserves user identities but removes tenant companies.  An
administrator account whose email domain identifies one imported company can
therefore be reattached deterministically after that company is recreated.
"""
import json
import re
import unicodedata

from django.core.management.base import BaseCommand

from apps.misc.api.models.companies.index import Empresa
from apps.users.api.models.index import SecurityRole, User, UserCompanyProfile
from apps.users.api.services import ensure_user_profile


def _key(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _company_key_from_email(email):
    host = str(email or "").split("@")[-1].split(".")[0]
    return _key(host)


class Command(BaseCommand):
    help = "Restaura automáticamente la empresa de administradores tras una importación histórica."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        role = SecurityRole.objects.filter(code="admin_empresa", active=True).first()
        if not role:
            self.stderr.write("No existe el rol admin_empresa; no se restauraron administradores.")
            return

        companies = list(Empresa.objects.filter(is_internal=False, is_active=True).order_by("id"))
        restored = []
        ambiguous = []
        candidates = User.objects.filter(
            empresa__isnull=True,
            role=User.Role.ADMIN,
            is_active=True,
        ).order_by("id")
        for user in candidates:
            domain_key = _company_key_from_email(user.email)
            matches = [company for company in companies if domain_key and _key(company.nombre).startswith(domain_key)]
            if len(matches) != 1:
                if len(matches) > 1:
                    ambiguous.append(user.email)
                continue
            company = matches[0]
            restored.append({"email": user.email, "empresa": company.nombre})
            if options["dry_run"]:
                continue
            user.empresa = company
            user.data_scope_override = ""
            user.home_path = ""
            user.save(update_fields=["empresa", "data_scope_override", "home_path"])
            profile = ensure_user_profile(
                user,
                company,
                role=role,
                is_company_admin=True,
                status=UserCompanyProfile.Status.ACTIVE,
            )
            if not profile.activated_at:
                from django.utils import timezone
                profile.activated_at = timezone.now()
                profile.save(update_fields=["activated_at", "updated_at"])

        self.stdout.write(json.dumps({
            "mode": "dry_run" if options["dry_run"] else "apply",
            "administradores_restaurados": restored,
            "administradores_ambiguos": ambiguous,
        }, ensure_ascii=False))
