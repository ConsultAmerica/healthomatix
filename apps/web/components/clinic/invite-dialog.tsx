"use client";

import { useState, type FormEvent } from "react";
import { api, call, type ApiProblem, type Schemas } from "@/lib/api";
import { formatDateTime } from "@/lib/time";
import { CopyButton, Dialog, FormError, Notice, SelectField, SubmitButton } from "@/components/ui";
import { useActiveMembership } from "@/components/portal/portal-context";

type InviteRole = "staff" | "provider" | "patient";

const ROLE_COPY: Record<InviteRole, string> = {
  patient: "Patient — can book appointments and manage their own profile and consent.",
  staff: "Clinic staff — can view the patient roster and invite patients.",
  provider: "Provider — can manage their profile, credentials, and availability.",
};

export function InviteDialog({
  open,
  onClose,
  onCreated,
  defaultRole = "patient",
}: {
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
  defaultRole?: InviteRole;
}) {
  const membership = useActiveMembership();
  const allowed: InviteRole[] = membership.role === "tenant_admin" ? ["staff", "provider", "patient"] : ["patient"];
  const [role, setRole] = useState<InviteRole>(allowed.includes(defaultRole) ? defaultRole : "patient");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [created, setCreated] = useState<Schemas["InvitationCreated"] | null>(null);

  function close() {
    setCreated(null);
    setProblem(null);
    onClose();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/invitations", {
        params: { path: { tenant_id: membership.tenant_id } },
        body: { role },
      }),
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setCreated(result.data);
    onCreated?.();
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title={created ? "Share this invitation code" : "Create an invitation"}
      description={
        created
          ? "This code is shown only once. Share it privately with the person you're inviting."
          : `Invite someone to ${membership.tenant_name}. Codes are single-use and expire after seven days.`
      }
    >
      {created ? (
        <div className="form-stack">
          <div className="secret-box">
            <code aria-label="Invitation code">{created.invitation_code}</code>
          </div>
          <div className="form-actions">
            <CopyButton value={created.invitation_code} label="Copy code" />
            <button className="button button-small" type="button" onClick={close}>
              Done
            </button>
          </div>
          <Notice title={`Expires ${formatDateTime(created.expires_at)}`} tone="warning">
            Healthomatix doesn&apos;t send this code by email. Share it through a secure channel, never in a public
            message.
          </Notice>
        </div>
      ) : (
        <form className="form-stack" onSubmit={submit}>
          <FormError problem={problem} />
          <SelectField
            label="Role"
            value={role}
            onChange={(event) => setRole(event.target.value as InviteRole)}
            hint={ROLE_COPY[role]}
          >
            {allowed.map((value) => (
              <option key={value} value={value}>
                {value === "staff" ? "Clinic staff" : value.charAt(0).toUpperCase() + value.slice(1)}
              </option>
            ))}
          </SelectField>
          <div className="form-actions">
            <button className="button button-light button-small" type="button" onClick={close}>
              Cancel
            </button>
            <SubmitButton pending={pending} pendingLabel="Creating…">
              Create code
            </SubmitButton>
          </div>
        </form>
      )}
    </Dialog>
  );
}
