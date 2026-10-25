"""The lead-intake request shape, in one place: the Pydantic model the intake
endpoint validates against (module_packages/contacts/backend/router_intake.py)
AND a plain-language field list + ready-to-copy example built from that same
model, so the docs can never drift from what the endpoint actually accepts.

The spec is shown on Admin → Integrations & MCP (with an integration key's
reveal and its "How to send leads" view) and served at
GET /api/v1/contacts/intake/lead for anything that wants to discover the
fields itself (an n8n/Zapier step, a developer, an AI writing the form code).
Core, not inside the Contacts module, because the admin page (core) shows it
regardless — same reasoning contacts_service.py itself stays core."""

from pydantic import BaseModel, Field

INTAKE_PATH = "/api/v1/contacts/intake/lead"


class LeadIntake(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=200, description="The person's name.", examples=["Dana Smith"]
    )
    phone: str = Field(
        ...,
        min_length=7,
        max_length=40,
        description=(
            "Phone number in any format, at least 7 digits. Used to recognize a repeat lead "
            "from the same person, so it's merged instead of duplicated."
        ),
        examples=["(501) 555-0100"],
    )
    email: str | None = Field(
        default=None, max_length=200, description="Email address.", examples=["dana@example.com"]
    )
    message: str = Field(
        default="",
        max_length=5000,
        description="What they wrote — saved as a note on the contact.",
        examples=["Please call me back about a quote — weekday mornings are best."],
    )
    source: str = Field(
        default="",
        max_length=40,
        description="Where the lead came from — shown on the note and added as a tag.",
        examples=["Website"],
    )
    external_id: str | None = Field(
        default=None,
        max_length=128,
        description="Your own id for this submission, if any — also used to avoid duplicates.",
        examples=["form-123"],
    )
    follow_up_days: int = Field(
        default=1,
        ge=0,
        le=365,
        description="Days from today until the follow-up reminder (0 = today).",
        examples=[1],
    )


def intake_spec() -> dict:
    """Everything a caller needs to send a lead, derived from LeadIntake."""
    schema = LeadIntake.model_json_schema()
    required = set(schema.get("required", []))
    fields = []
    example: dict = {}
    for name, prop in schema["properties"].items():
        kind = prop.get("type") or next(
            (o.get("type") for o in prop.get("anyOf", []) if o.get("type") != "null"), "string"
        )
        sample = (prop.get("examples") or [None])[0]
        fields.append(
            {
                "name": name,
                "type": kind,
                "required": name in required,
                "description": prop.get("description", ""),
                "example": sample,
            }
        )
        if sample is not None:
            example[name] = sample
    return {
        "method": "POST",
        "path": INTAKE_PATH,
        "headers": {
            "Authorization": "Bearer <your integration key>",
            "Content-Type": "application/json",
        },
        "fields": fields,
        "example": example,
        "response": {
            "ok": True,
            "contact_id": "…",
            "interaction_id": "…",
            "created": "true for a new contact, false when merged into an existing one",
        },
        "schema": schema,
    }
