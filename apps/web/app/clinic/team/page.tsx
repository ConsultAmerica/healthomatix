"use client";

import { useState } from "react";
import { InviteDialog } from "@/components/clinic/invite-dialog";
import { RoleGate } from "@/components/portal/portal-shell";
import { ROLE_LABELS, useActiveMembership, usePortal } from "@/components/portal/portal-context";
import { Dialog, EmptyState, FormError, PageHeader, QueryView, Section, StatusBadge, Table, useToast } from "@/components/ui";
import { api, call, useApiQuery, type ApiProblem, type Schemas } from "@/lib/api";
import { formatDate, formatDateTime, isFuture, shortId } from "@/lib/time";

export default function TeamPage() {
  return (
    <RoleGate roles={["tenant_admin"]}>
      <Team />
    </RoleGate>
  );
}

function invitationStatus(invite: Schemas["InvitationRead"]) {
  return invite.status === "pending" && !isFuture(invite.expires_at) ? "expired" : invite.status;
}

function Team() {
  const membership = useActiveMembership();
  const { state: portalState } = usePortal();
  const myUserId = portalState.status === "ready" ? portalState.user.user_id : null;
  const tenant_id = membership.tenant_id;
  const notify = useToast();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [revoking, setRevoking] = useState<Schemas["InvitationRead"] | null>(null);
  const [revokeProblem, setRevokeProblem] = useState<ApiProblem | null>(null);
  const [revokePending, setRevokePending] = useState(false);
  const path = { params: { path: { tenant_id } } };

  const members = useApiQuery(`members:${tenant_id}`, () => call(api().GET("/api/v1/tenants/{tenant_id}/members", path)));
  const invitations = useApiQuery(`invitations:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/invitations", path)),
  );

  async function revoke() {
    if (!revoking) return;
    setRevokePending(true);
    setRevokeProblem(null);
    const result = await call(
      api().DELETE("/api/v1/tenants/{tenant_id}/invitations/{invitation_id}", {
        params: { path: { tenant_id, invitation_id: revoking.invitation_id } },
      }),
    );
    setRevokePending(false);
    if (!result.ok) {
      setRevokeProblem(result.problem);
      return;
    }
    setRevoking(null);
    notify("Invitation revoked. The code can no longer be used.");
    invitations.reload();
  }

  return (
    <>
      <PageHeader
        eyebrow="TEAM"
        title="Team and invitations"
        description={`Everyone with access to ${membership.tenant_name}, and invitations that haven't been used yet.`}
        actions={
          <button className="button button-small" type="button" onClick={() => setInviteOpen(true)}>
            Invite someone
          </button>
        }
      />

      <Section title="Members" description="Contact details are managed by your identity provider and aren't stored here.">
        <QueryView state={members.state} onRetry={members.reload} rows={4} loadingLabel="Loading members">
          {(rows) =>
            rows.length ? (
              <Table caption="Clinic members">
                <thead>
                  <tr>
                    <th scope="col">Member</th>
                    <th scope="col">Role</th>
                    <th scope="col">Status</th>
                    <th scope="col">Since</th>
                    <th scope="col">
                      <span className="visually-hidden">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[...rows]
                    .sort((a, b) => Number(b.user_id === myUserId) - Number(a.user_id === myUserId))
                    .map((member) => (
                    <tr key={member.user_id}>
                      <td>
                        <span className="member-cell">
                          <span className={`member-avatar role-${member.role}`} aria-hidden="true">
                            {(ROLE_LABELS[member.role] ?? member.role).charAt(0)}
                          </span>
                          <span>
                            <strong className="cell-title">
                              {member.user_id === myUserId ? "You" : `Member ${shortId(member.user_id)}`}
                            </strong>
                            <span className="cell-sub">Identity managed by your sign-in provider</span>
                          </span>
                        </span>
                      </td>
                      <td>{ROLE_LABELS[member.role] ?? member.role}</td>
                      <td>
                        <StatusBadge status={member.status} />
                      </td>
                      <td>{formatDate(member.created_at)}</td>
                      <td>
                        {member.user_id !== myUserId && member.status === "active" ? (
                          <button
                            className="button button-small button-light"
                            type="button"
                            onClick={async () => {
                              const result = await call(
                                api().POST("/api/v1/tenants/{tenant_id}/members/{user_id}/deactivate", {
                                  params: { path: { tenant_id, user_id: member.user_id } },
                                }),
                              );
                              if (result.ok) {
                                notify("Member deactivated.");
                                members.reload();
                              } else {
                                notify(result.problem.message);
                              }
                            }}
                          >
                            Deactivate
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="No members yet" />
            )
          }
        </QueryView>
      </Section>

      <Section
        title="Invitations"
        description="Codes are shown once when created. Revoke any code that may have been shared with the wrong person."
        actions={
          <label className="toggle">
            <input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} />
            Show used and expired
          </label>
        }
      >
        <QueryView state={invitations.state} onRetry={invitations.reload} rows={3} loadingLabel="Loading invitations">
          {(rows) => {
            const visible = showAll ? rows : rows.filter((invite) => invitationStatus(invite) === "pending");
            if (!visible.length) {
              return (
                <EmptyState
                  title={showAll ? "No invitations yet" : "No open invitations"}
                  action={
                    <button className="button button-small" type="button" onClick={() => setInviteOpen(true)}>
                      Create an invitation
                    </button>
                  }
                />
              );
            }
            return (
              <Table caption="Invitations">
                <thead>
                  <tr>
                    <th scope="col">Role</th>
                    <th scope="col">Status</th>
                    <th scope="col">Created</th>
                    <th scope="col">Expires</th>
                    <th scope="col">
                      <span className="visually-hidden">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((invite) => {
                    const status = invitationStatus(invite);
                    return (
                      <tr key={invite.invitation_id}>
                        <td>{ROLE_LABELS[invite.role] ?? invite.role}</td>
                        <td>
                          <StatusBadge status={status} />
                        </td>
                        <td>{formatDateTime(invite.created_at)}</td>
                        <td>{formatDateTime(invite.expires_at)}</td>
                        <td className="cell-actions">
                          {status === "pending" && (
                            <button
                              className="button button-ghost-danger button-small"
                              type="button"
                              onClick={() => {
                                setRevokeProblem(null);
                                setRevoking(invite);
                              }}
                            >
                              Revoke
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            );
          }}
        </QueryView>
      </Section>

      <InviteDialog
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        onCreated={invitations.reload}
        defaultRole="staff"
      />

      <Dialog
        open={revoking !== null}
        onClose={() => setRevoking(null)}
        title="Revoke this invitation?"
        description="Anyone holding this code will no longer be able to join. This can't be undone."
      >
        <div className="form-stack">
          <FormError problem={revokeProblem} />
          <div className="form-actions">
            <button className="button button-light button-small" type="button" onClick={() => setRevoking(null)}>
              Keep invitation
            </button>
            <button
              className="button button-danger button-small"
              type="button"
              onClick={revoke}
              disabled={revokePending}
              aria-busy={revokePending}
            >
              {revokePending ? "Revoking…" : "Revoke invitation"}
            </button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
