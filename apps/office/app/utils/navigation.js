// Copyright 2026 Signet Team
// SPDX-License-Identifier: Apache-2.0

export function primaryNavigation(role, t) {
  const items = [];
  if (role && role !== 'tenant_admin') items.push({
    to: '/',
    label: t('nav.inbox'),
    icon: 'M3 7l9 6 9-6M5 5h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2z'
  });
  if (role && role !== 'tenant_admin') items.push({
    to: '/van-ban-den',
    label: t('nav.incoming'),
    icon: 'M4 4h10l6 6v10a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1zm10 0v6h6'
  });
  if (role === 'clerk') items.push({
    to: '/van-ban-den/tiep-nhan',
    label: t('nav.receive'),
    icon: 'M12 5v14m-7-7h14'
  });
  if (role && role !== 'tenant_admin') items.push({
    to: '/van-ban-di',
    label: t('nav.outgoing'),
    icon: 'M4 12l16-8-6 16-2-7-8-1z'
  });
  if (role === 'clerk' || role === 'director') items.push({
    to: '/so-dang-ky',
    label: t('nav.register'),
    icon: 'M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2V5zm0 16a2 2 0 012-2h13v2H6a2 2 0 01-2 0zM8 7h7M8 11h7'
  });
  if (['clerk', 'staff', 'manager', 'director'].includes(role)) items.push({ to: '/hoi-dap', label: t('nav.ask'), icon: 'M8 10h8M8 14h5M21 12a9 9 0 01-13.2 8L3 21l1.1-4.6A9 9 0 1121 12z' });
  if (role === 'director') items.push({
    to: '/dieu-hanh',
    label: t('nav.board'),
    icon: 'M3 3v18h18M8 17v-4m4 4V8m4 9v-6'
  });
  if (role === 'director' || role === 'tenant_admin') items.push({
    to: '/so-kiem-toan',
    label: t('nav.audit'),
    icon: 'M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6l7-3zm-3 9l2 2 4-4'
  });
  if (role && role !== 'tenant_admin') items.push({ to: '/ho-so', label: t('cases.title'), icon: 'M3 7h7l2 2h9v11H3V7zm0 0V4h7l2 3' });
  return items;
}

export function toolNavigation(role, t) {
  if (!role) return [];
  const items = [];
  if (['clerk', 'staff', 'manager', 'director'].includes(role)) items.push({ to: '/cam-bien', label: t('nav.sensors'), icon: 'M3 5h18v14H3zM3 11h7m4 0h7M9 5v6m6-6v6m-3 2v6' });
  if (role === 'director') {
    items.push({ to: '/so-do', label: t('nav.metrics'), icon: 'M12 9v4l2.5 2.5M9 3h6M12 21a8 8 0 110-16 8 8 0 010 16z' });
    items.push({ to: '/pha-he', label: t('lineage.nav'), icon: 'M4 9h5v6H4zM15 3h5v6h-5zM15 15h5v6h-5zM9 12h3m0-6v12m0-12h3m-3 12h3' });
  }
  if (['director', 'manager'].includes(role)) items.push({ to: '/tu-chan-doan', label: t('nav.selfCheck'), icon: 'M9 3h6v3H9zM7 5H4v16h16V5h-3M8 12l2 2 5-5M8 18h8' });
  items.push({ to: '/ung-dung', label: t('apps.nav'), icon: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z' });
  items.push({ to: '/gop-y', label: t('nav.feedback'), icon: 'M8 10h8M8 14h5M21 12a9 9 0 01-13.2 8L3 21l1.1-4.6A9 9 0 1121 12z' });
  return items;
}

export function allNavigation(role, t = key => key) {
  if (!role) return [];
  return [...primaryNavigation(role, t), ...toolNavigation(role, t), { to: '/tim-kiem', label: t('nav.search') }];
}
