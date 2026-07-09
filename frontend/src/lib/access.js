export const canAdministerMemory = (user) => Boolean(user?.is_admin);

export const visibleSettingsTabs = (tabs, user) =>
  tabs.filter((tab) => !tab.adminOnly || canAdministerMemory(user));
