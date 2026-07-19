/**
 * FlowPilot FastAPI kaynak fonksiyonları — YALNIZ SERVER-SIDE, typed + zod-doğrulanmış.
 *
 * Her fonksiyon backend yanıtını Zod ile KÖR GÜVENMEDEN doğrular ve snake_case
 * transport'u camelCase domain tipine eşler. Bearer token yalnız server'da; hata
 * durumları `ApiFailure`'a güvenli biçimde eşlenir (bkz. http.ts).
 */

import "server-only";

import { z } from "zod";

import { apiRequest, type ApiOutcome } from "@/lib/api/http";

// --------------------------------------------------------------- ortak yardımcı

type RawResult = Awaited<ReturnType<typeof apiRequest>>;

function parseOk<TIn, TOut>(
  raw: RawResult,
  schema: z.ZodType<TIn>,
  map: (value: TIn) => TOut,
): ApiOutcome<TOut> {
  if (raw.kind !== "ok") {
    return raw;
  }
  const parsed = schema.safeParse(raw.json);
  if (!parsed.success) {
    // Beklenmeyen/bozuk gövde kullanıcıya taşınmaz — kontrollü server_error.
    return { kind: "server_error" };
  }
  return { kind: "ok", data: map(parsed.data) };
}

const uuid = z.uuid();
const timestamp = z.string().min(1);
const amountMinor = z.number().int().nonnegative();
const nullableString = z.string().nullable();

// ------------------------------------------------------------------- şemalar

const myOrganizationsSchema = z.object({
  items: z.array(
    z.object({
      organization_id: uuid,
      name: z.string(),
      membership_kind: z.string(),
      membership_status: z.string(),
    }),
  ),
});

const createdPurchaseRequestSchema = z.object({
  purchase_request_id: uuid,
  organization_id: uuid,
  workflow_instance_id: uuid,
  status: z.string(),
  title: z.string(),
  amount_minor: amountMinor,
  currency: z.string(),
  current_approval_role: nullableString,
  created_at: timestamp,
});

const purchaseRequestListSchema = z.object({
  items: z.array(
    z.object({
      purchase_request_id: uuid,
      title: z.string(),
      amount_minor: amountMinor,
      currency: z.string(),
      status: z.string(),
      current_approval_role: nullableString,
      created_at: timestamp,
      updated_at: timestamp,
    }),
  ),
});

const purchaseRequestDetailSchema = z.object({
  purchase_request_id: uuid,
  organization_id: uuid,
  requested_by_current_user: z.boolean(),
  title: z.string(),
  description: nullableString,
  amount_minor: amountMinor,
  currency: z.string(),
  status: z.string(),
  workflow_instance_id: uuid.nullable(),
  workflow_status: nullableString,
  current_approval_role: nullableString,
  created_at: timestamp,
  updated_at: timestamp,
});

const timelineSchema = z.object({
  purchase_request_id: uuid,
  items: z.array(
    z.object({
      event_type: z.string(),
      occurred_at: timestamp,
      actor_is_current_user: z.boolean(),
      role_key: nullableString,
      task_id: uuid.nullable(),
      message: z.string(),
    }),
  ),
});

const inboxSchema = z.object({
  items: z.array(
    z.object({
      task_id: uuid,
      purchase_request_id: uuid,
      purchase_request_title: z.string(),
      amount_minor: amountMinor,
      currency: z.string(),
      required_role: z.string(),
      status: z.string(),
      workflow_instance_id: uuid,
      created_at: timestamp,
      due_at: z.string().nullable(),
    }),
  ),
});

const decisionSchema = z.object({
  task_id: uuid,
  decision: z.string(),
  purchase_request_id: uuid,
  purchase_request_status: z.string(),
  workflow_status: z.string(),
  next_approval_role: nullableString,
  decided_at: timestamp,
  duplicate: z.boolean(),
});

// ---------------------------------------------------------------- domain tipleri

export interface MyOrganization {
  readonly organizationId: string;
  readonly name: string;
  readonly membershipKind: string;
  readonly membershipStatus: string;
}

export interface CreatedPurchaseRequest {
  readonly purchaseRequestId: string;
  readonly organizationId: string;
  readonly workflowInstanceId: string;
  readonly status: string;
  readonly title: string;
  readonly amountMinor: number;
  readonly currency: string;
  readonly currentApprovalRole: string | null;
  readonly createdAt: string;
}

export interface PurchaseRequestListItem {
  readonly purchaseRequestId: string;
  readonly title: string;
  readonly amountMinor: number;
  readonly currency: string;
  readonly status: string;
  readonly currentApprovalRole: string | null;
  readonly createdAt: string;
  readonly updatedAt: string;
}

export interface PurchaseRequestDetail {
  readonly purchaseRequestId: string;
  readonly organizationId: string;
  readonly requestedByCurrentUser: boolean;
  readonly title: string;
  readonly description: string | null;
  readonly amountMinor: number;
  readonly currency: string;
  readonly status: string;
  readonly workflowInstanceId: string | null;
  readonly workflowStatus: string | null;
  readonly currentApprovalRole: string | null;
  readonly createdAt: string;
  readonly updatedAt: string;
}

export interface TimelineItem {
  readonly eventType: string;
  readonly occurredAt: string;
  readonly actorIsCurrentUser: boolean;
  readonly roleKey: string | null;
  readonly taskId: string | null;
  readonly message: string;
}

export interface InboxItem {
  readonly taskId: string;
  readonly purchaseRequestId: string;
  readonly purchaseRequestTitle: string;
  readonly amountMinor: number;
  readonly currency: string;
  readonly requiredRole: string;
  readonly status: string;
  readonly workflowInstanceId: string;
  readonly createdAt: string;
  readonly dueAt: string | null;
}

export interface DecisionResult {
  readonly taskId: string;
  readonly decision: string;
  readonly purchaseRequestId: string;
  readonly purchaseRequestStatus: string;
  readonly workflowStatus: string;
  readonly nextApprovalRole: string | null;
  readonly decidedAt: string;
  readonly duplicate: boolean;
}

export interface CreatePurchaseRequestInput {
  readonly title: string;
  readonly description: string | null;
  readonly amountMinor: number;
  readonly currency: string;
}

export interface DecideApprovalTaskInput {
  readonly decision: "approve" | "reject";
  readonly comment: string | null;
  readonly idempotencyKey: string;
}

// -------------------------------------------------------------------- fonksiyonlar

const orgBase = (organizationId: string) => `/v1/organizations/${organizationId}`;

export async function listMyOrganizations(
  accessToken: string,
): Promise<ApiOutcome<readonly MyOrganization[]>> {
  const raw = await apiRequest({ method: "GET", path: "/v1/me/organizations", accessToken });
  return parseOk(raw, myOrganizationsSchema, (value) =>
    value.items.map((item) => ({
      organizationId: item.organization_id,
      name: item.name,
      membershipKind: item.membership_kind,
      membershipStatus: item.membership_status,
    })),
  );
}

export async function createPurchaseRequest(
  accessToken: string,
  organizationId: string,
  input: CreatePurchaseRequestInput,
): Promise<ApiOutcome<CreatedPurchaseRequest>> {
  const raw = await apiRequest({
    method: "POST",
    path: `${orgBase(organizationId)}/purchase-requests`,
    accessToken,
    body: {
      title: input.title,
      description: input.description,
      amount_minor: input.amountMinor,
      currency: input.currency,
    },
  });
  return parseOk(raw, createdPurchaseRequestSchema, (value) => ({
    purchaseRequestId: value.purchase_request_id,
    organizationId: value.organization_id,
    workflowInstanceId: value.workflow_instance_id,
    status: value.status,
    title: value.title,
    amountMinor: value.amount_minor,
    currency: value.currency,
    currentApprovalRole: value.current_approval_role,
    createdAt: value.created_at,
  }));
}

export async function listMyPurchaseRequests(
  accessToken: string,
  organizationId: string,
): Promise<ApiOutcome<readonly PurchaseRequestListItem[]>> {
  const raw = await apiRequest({
    method: "GET",
    path: `${orgBase(organizationId)}/purchase-requests`,
    accessToken,
  });
  return parseOk(raw, purchaseRequestListSchema, (value) =>
    value.items.map((item) => ({
      purchaseRequestId: item.purchase_request_id,
      title: item.title,
      amountMinor: item.amount_minor,
      currency: item.currency,
      status: item.status,
      currentApprovalRole: item.current_approval_role,
      createdAt: item.created_at,
      updatedAt: item.updated_at,
    })),
  );
}

export async function getPurchaseRequest(
  accessToken: string,
  organizationId: string,
  purchaseRequestId: string,
): Promise<ApiOutcome<PurchaseRequestDetail>> {
  const raw = await apiRequest({
    method: "GET",
    path: `${orgBase(organizationId)}/purchase-requests/${purchaseRequestId}`,
    accessToken,
  });
  return parseOk(raw, purchaseRequestDetailSchema, (value) => ({
    purchaseRequestId: value.purchase_request_id,
    organizationId: value.organization_id,
    requestedByCurrentUser: value.requested_by_current_user,
    title: value.title,
    description: value.description,
    amountMinor: value.amount_minor,
    currency: value.currency,
    status: value.status,
    workflowInstanceId: value.workflow_instance_id,
    workflowStatus: value.workflow_status,
    currentApprovalRole: value.current_approval_role,
    createdAt: value.created_at,
    updatedAt: value.updated_at,
  }));
}

export async function getPurchaseRequestTimeline(
  accessToken: string,
  organizationId: string,
  purchaseRequestId: string,
): Promise<ApiOutcome<readonly TimelineItem[]>> {
  const raw = await apiRequest({
    method: "GET",
    path: `${orgBase(organizationId)}/purchase-requests/${purchaseRequestId}/timeline`,
    accessToken,
  });
  return parseOk(raw, timelineSchema, (value) =>
    value.items.map((item) => ({
      eventType: item.event_type,
      occurredAt: item.occurred_at,
      actorIsCurrentUser: item.actor_is_current_user,
      roleKey: item.role_key,
      taskId: item.task_id,
      message: item.message,
    })),
  );
}

export async function getMyTaskInbox(
  accessToken: string,
  organizationId: string,
): Promise<ApiOutcome<readonly InboxItem[]>> {
  const raw = await apiRequest({
    method: "GET",
    path: `${orgBase(organizationId)}/tasks/inbox`,
    accessToken,
  });
  return parseOk(raw, inboxSchema, (value) =>
    value.items.map((item) => ({
      taskId: item.task_id,
      purchaseRequestId: item.purchase_request_id,
      purchaseRequestTitle: item.purchase_request_title,
      amountMinor: item.amount_minor,
      currency: item.currency,
      requiredRole: item.required_role,
      status: item.status,
      workflowInstanceId: item.workflow_instance_id,
      createdAt: item.created_at,
      dueAt: item.due_at,
    })),
  );
}

export async function decideApprovalTask(
  accessToken: string,
  organizationId: string,
  taskId: string,
  input: DecideApprovalTaskInput,
): Promise<ApiOutcome<DecisionResult>> {
  const raw = await apiRequest({
    method: "POST",
    path: `${orgBase(organizationId)}/tasks/${taskId}/decision`,
    accessToken,
    body: { decision: input.decision, comment: input.comment },
    extraHeaders: { "Idempotency-Key": input.idempotencyKey },
  });
  return parseOk(raw, decisionSchema, (value) => ({
    taskId: value.task_id,
    decision: value.decision,
    purchaseRequestId: value.purchase_request_id,
    purchaseRequestStatus: value.purchase_request_status,
    workflowStatus: value.workflow_status,
    nextApprovalRole: value.next_approval_role,
    decidedAt: value.decided_at,
    duplicate: value.duplicate,
  }));
}
