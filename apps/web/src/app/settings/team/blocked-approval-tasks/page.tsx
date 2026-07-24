import type { Metadata } from "next";

import { Alert } from "@/components/alert";
import { AppShell } from "@/components/app-shell";
import { ButtonLink } from "@/components/button";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { ServiceUnavailable } from "@/components/service-unavailable";
import { resolveBlockedTaskAction } from "@/features/blocked-tasks/actions";
import { BlockedTaskList } from "@/features/blocked-tasks/blocked-task-list";
import { canManageBlockedTasks } from "@/features/blocked-tasks/permissions";
import { getUserEmail, requireActiveOrganization } from "@/features/organizations/context";
import { listBlockedApprovalTasks, listOrganizationMembers } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Engellenen Onaylar" };

const BLOCKED_TASKS_PATH = "/settings/team/blocked-approval-tasks";

export default async function BlockedApprovalTasksPage() {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return <ServiceUnavailable retryHref={BLOCKED_TASKS_PATH} />;
  }

  const userEmail = await getUserEmail();
  const canManage = canManageBlockedTasks(context.organization.membershipKind);

  if (!canManage) {
    // Frontend görünürlüğü UX içindir; backend zaten reddeder. Kaynak sızdırmadan güvenli mesaj.
    return (
      <AppShell
        userEmail={userEmail}
        organizationName={context.organization.name}
        activeNav="blocked-tasks"
        canManage={false}
      >
        <PageHeader title="Engellenen Onay Görevleri" description="Engellenen onayları görüntüleyin." />
        <Alert tone="error">Bu sayfaya erişim yetkiniz yok.</Alert>
      </AppShell>
    );
  }

  const [tasksOutcome, membersOutcome] = await Promise.all([
    listBlockedApprovalTasks(context.accessToken, context.organization.organizationId),
    listOrganizationMembers(context.accessToken, context.organization.organizationId),
  ]);

  return (
    <AppShell
      userEmail={userEmail}
      organizationName={context.organization.name}
      activeNav="blocked-tasks"
      canManage
    >
      <PageHeader
        title="Engellenen Onay Görevleri"
        description="Uygun onaycı atanamadığı için ilerleyemeyen onay görevlerini görüntüleyin ve atama sorunlarını çözün."
      />

      <div className="mb-4">
        <Alert tone="info">
          Bu işlem yalnız seçilen mevcut görevin atamasını çözer; onay rolü yapılandırmasını
          değiştirmez.
        </Alert>
      </div>

      {tasksOutcome.kind !== "ok" ? (
        <div className="flex flex-col items-start gap-3">
          <Alert tone="error">
            Engellenen onay görevleri şu anda getirilemedi. Lütfen tekrar deneyin.
          </Alert>
          <ButtonLink href={BLOCKED_TASKS_PATH} variant="secondary">
            Tekrar dene
          </ButtonLink>
        </div>
      ) : tasksOutcome.data.length === 0 ? (
        <EmptyState
          title="Bekleyen atama sorunu yok"
          description="Şu anda atama sorunu nedeniyle bekleyen onay görevi bulunmuyor."
          icon="✅"
        />
      ) : (
        <BlockedTaskList
          tasks={tasksOutcome.data}
          members={membersOutcome.kind === "ok" ? membersOutcome.data : []}
          action={resolveBlockedTaskAction}
        />
      )}
    </AppShell>
  );
}
