const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  user: null,
  patients: [],
  appointments: [],
  dentists: [],
  staff: [],
  xrays: [],
  xrayObjectUrls: new Map(),
  view: 'dashboard',
};

const viewPaths = {
  dashboard: '/',
  patients: '/patients/',
  appointments: '/appointments/',
  finances: '/finances/',
  xrays: '/xrays/',
  team: '/team/',
};

function viewFromPath() {
  return Object.entries(viewPaths).find(([, path]) => path === window.location.pathname)?.[0] || 'dashboard';
}

const auth = {
  get clinic() { return sessionStorage.getItem('clinic'); },
  get access() { return sessionStorage.getItem('access'); },
  get refresh() { return sessionStorage.getItem('refresh'); },
  save(tokens) {
    if (tokens.access) sessionStorage.setItem('access', tokens.access);
    if (tokens.refresh) sessionStorage.setItem('refresh', tokens.refresh);
  },
  clear() { sessionStorage.removeItem('clinic'); sessionStorage.removeItem('access'); sessionStorage.removeItem('refresh'); },
};

function escapeHtml(value = '') {
  return String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
}

function initials(name = '') {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase() || '—';
}

function list(payload) { return Array.isArray(payload) ? payload : (payload?.results || []); }
function fullName(person) { return [person?.first_name, person?.last_name].filter(Boolean).join(' ') || person?.username || 'Staff member'; }
function isAdminUser() { return Boolean(state.user && (state.user.role === 'admin')); }
function isReceptionistUser() { return state.user?.role === 'receptionist' && !isAdminUser(); }
function isDentistUser() { return state.user?.role === 'dentist' && !isAdminUser(); }
function canManageSchedule() { return isAdminUser() || isReceptionistUser(); }
function canCreatePatients() { return isAdminUser() || isReceptionistUser(); }
function canEditClinicalOutcome() { return isAdminUser() || isDentistUser(); }
function canManageInvoices() { return isAdminUser() || isReceptionistUser(); }
function canDeleteXrays() { return isAdminUser() || isDentistUser(); }
function currency(value, code = 'USD') { return new Intl.NumberFormat(undefined, {style:'currency', currency:code}).format(Number(value || 0)); }
function currencyTotals(items, valueSelector) {
  const totals = items.reduce((result, item) => {
    const code = item.invoice?.currency || 'USD';
    result[code] = (result[code] || 0) + Number(valueSelector(item) || 0);
    return result;
  }, {});
  return Object.entries(totals).map(([code, value]) => currency(value, code)).join(' · ') || currency(0);
}
function dateTime(value) {
  if (!value) return 'Not recorded';
  return new Intl.DateTimeFormat(undefined, {month:'short', day:'numeric', year:'numeric', hour:'numeric', minute:'2-digit'}).format(new Date(value));
}
function dayTime(value) {
  const date = new Date(value);
  return {time: new Intl.DateTimeFormat(undefined, {hour:'numeric', minute:'2-digit'}).format(date), day: new Intl.DateTimeFormat(undefined, {month:'short', day:'numeric'}).format(date)};
}
function statusClass(value = '') { return `status status-${value}`; }
function patientLabel(patient) {
  return `${patient.id} - ${patient.full_name}${patient.phone ? ` - ${patient.phone}` : ''}`;
}
function patientPicker(patients, selectedId = null, listId = 'patient-options') {
  const selected = patients.find(patient => patient.id === Number(selectedId));
  return `<input type="search" name="patient_search" list="${listId}" value="${selected ? escapeHtml(patientLabel(selected)) : ''}" placeholder="Start typing a patient name or phone…" autocomplete="off" required>
    <datalist id="${listId}">${patients.map(patient => `<option value="${escapeHtml(patientLabel(patient))}"></option>`).join('')}</datalist>`;
}
function selectedPatientId(form) {
  const value = form.elements.patient_search?.value.trim() || '';
  const match = state.patients.find(patient => patientLabel(patient) === value);
  return match?.id || null;
}
function xrayGallery(items, emptyText = 'No X-rays are attached yet.') {
  if (!items.length) return `<div class="record-empty">◇ ${escapeHtml(emptyText)}</div>`;
  return `<div class="record-images">${items.map(xray => {
    const image = xray.image_cloud || xray.image_local;
    const preview = image ? `<img data-protected-src="${escapeHtml(image)}" alt="${escapeHtml(xray.description || 'Dental X-ray')}">` : '<span>◇</span>';
    return `<button type="button" class="record-image" data-action="view-xray" data-id="${xray.id}" data-url="${escapeHtml(image)}" data-description="${escapeHtml(xray.description || 'Dental X-ray')}">${preview}<span><strong>${escapeHtml(xray.description || 'Dental X-ray')}</strong><small>${dateTime(xray.taken_at || xray.imported_at)}</small></span></button>`;
  }).join('')}</div>`;
}
function apiError(data) {
  if (!data) return 'Something went wrong. Please try again.';
  if (typeof data === 'string') return data;
  if (data.detail) return data.detail;
  return Object.entries(data).map(([key, value]) => `${key.replaceAll('_', ' ')}: ${Array.isArray(value) ? value.join(' ') : value}`).join(' · ');
}

async function request(path, options = {}, retry = true) {
  const headers = new Headers(options.headers || {});
  if (auth.access) headers.set('Authorization', `Bearer ${auth.access}`);
  if (auth.clinic) headers.set('X-Clinic-ID', auth.clinic);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, {...options, headers});
  if (response.status === 401 && retry && auth.refresh && path !== '/api/accounts/token/refresh/') {
    const refreshResponse = await fetch('/api/accounts/token/refresh/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({refresh:auth.refresh})});
    if (refreshResponse.ok) {
      auth.save(await refreshResponse.json());
      return request(path, options, false);
    }
    logout();
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(apiError(data));
  return data;
}

async function protectedImageUrl(path, retry = true) {
  if (state.xrayObjectUrls.has(path)) return state.xrayObjectUrls.get(path);
  const response = await fetch(path, {
    headers: {'Authorization': `Bearer ${auth.access}`, 'X-Clinic-ID': auth.clinic || ''},
  });
  if (response.status === 401 && retry && auth.refresh) {
    const refreshResponse = await fetch('/api/accounts/token/refresh/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({refresh:auth.refresh})});
    if (refreshResponse.ok) {
      auth.save(await refreshResponse.json());
      return protectedImageUrl(path, false);
    }
    logout();
    throw new Error('Your session has expired.');
  }
  if (!response.ok) throw new Error('This X-ray image could not be loaded.');
  const objectUrl = URL.createObjectURL(await response.blob());
  state.xrayObjectUrls.set(path, objectUrl);
  return objectUrl;
}

async function hydrateProtectedImages(root = document) {
  await Promise.all($$('[data-protected-src]', root).map(async image => {
    try { image.src = await protectedImageUrl(image.dataset.protectedSrc); }
    catch { image.removeAttribute('src'); }
  }));
}

function clearProtectedImages() {
  state.xrayObjectUrls.forEach(url => URL.revokeObjectURL(url));
  state.xrayObjectUrls.clear();
}

function toast(message, type = 'success') {
  const node = document.createElement('div');
  node.className = `toast ${type}`;
  node.textContent = message;
  $('#toast-region').append(node);
  setTimeout(() => node.remove(), 3500);
}

function setLoading() { $('#main-content').innerHTML = '<div class="loading-state"><span class="spinner"></span>Loading clinic…</div>'; }
function openModal(content) { $('#modal-content').innerHTML = content; $('#modal').showModal(); }
function closeModal() { $('#modal').close(); }

async function login(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  const error = $('#login-error');
  button.disabled = true; error.textContent = '';
  try {
    const data = Object.fromEntries(new FormData(event.currentTarget));
    auth.save(await request('/api/accounts/login/', {method:'POST', body:JSON.stringify(data)}, false));
    await boot();
  } catch (err) {
    error.textContent = err.message === 'No active account found with the given credentials' ? 'That username or password is incorrect.' : err.message;
  } finally { button.disabled = false; }
}

function logout() {
  const refresh = auth.refresh;
  clearProtectedImages();
  auth.clear(); state.user = null;
  state.patients = []; state.appointments = []; state.dentists = []; state.staff = []; state.xrays = [];
  $('#main-content').replaceChildren();
  closeModal();
  $('#app-shell').classList.add('hidden');
  $('#login-screen').classList.remove('hidden');
  $('#login-form').reset();
  if (refresh) {
    fetch('/api/accounts/logout/', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({refresh}),
    }).catch(() => {});
  }
}

async function boot() {
  if (!auth.access) return logout();
  try {
    const memberships = await request('/api/accounts/memberships/');
    if (!memberships.length) throw new Error('No active clinic membership. Contact your administrator.');
    const active = memberships.find(m => String(m.clinic_id) === auth.clinic) || memberships[0];
    sessionStorage.setItem('clinic', active.clinic_id);
    const picker = $('#clinic-picker');
    picker.innerHTML = memberships.map(m => `<option value="${m.clinic_id}">${escapeHtml(m.clinic_name)}</option>`).join('');
    picker.value = String(active.clinic_id);
    picker.onchange = () => {
      sessionStorage.setItem('clinic', picker.value);
      // A full reload discards cached records, image blobs and in-flight UI work.
      window.location.reload();
    };
    state.user = await request('/api/accounts/me/');
    const name = fullName(state.user);
    $('#user-name').textContent = name;
    $('#user-role').textContent = state.user.role;
    $('#user-avatar').textContent = initials(name);
    $('#quick-add').classList.toggle('hidden', !canManageSchedule());
    $('#login-screen').classList.add('hidden');
    $('#app-shell').classList.remove('hidden');
    await navigate(viewFromPath(), false);
  } catch (error) { logout(); $('#login-error').textContent = error.message; }
}

async function ensureReferenceData() {
  const [patients, dentists] = await Promise.all([
    request('/api/patients/?ordering=full_name'),
    request('/api/accounts/dentists/'),
  ]);
  state.patients = list(patients); state.dentists = list(dentists);
}

function updateHeader(view) {
  const now = new Date();
  $('#page-kicker').textContent = new Intl.DateTimeFormat(undefined, {weekday:'long', month:'long', day:'numeric'}).format(now).toUpperCase();
  const titles = {dashboard:`Good ${now.getHours() < 12 ? 'morning' : now.getHours() < 18 ? 'afternoon' : 'evening'}`, patients:'Patient records', appointments:'Clinic schedule', finances:'Financial reporting', xrays:'Diagnostic imaging', team:'Your team'};
  $('#page-title').textContent = titles[view];
  $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === view));
}

async function navigate(view, updateUrl = true) {
  if (!viewPaths[view]) view = 'dashboard';
  if (updateUrl && window.location.pathname !== viewPaths[view]) {
    history.pushState({view}, '', viewPaths[view]);
  }
  state.view = view; updateHeader(view); setLoading(); closeSidebar();
  try {
    if (view === 'dashboard') await renderDashboard();
    if (view === 'patients') await renderPatients();
    if (view === 'appointments') await renderAppointments();
    if (view === 'finances') await renderFinances();
    if (view === 'xrays') await renderXrays();
    if (view === 'team') await renderTeam();
    $('#main-content').focus();
  } catch (err) {
    $('#main-content').innerHTML = `<div class="empty-state"><div class="empty-icon">!</div><h3>We couldn't load this page</h3><p>${escapeHtml(err.message)}</p><button class="btn btn-secondary" data-action="retry">Try again</button></div>`;
  }
}

async function renderDashboard() {
  const [patients, appointments] = await Promise.all([request('/api/patients/'), request('/api/appointments/?ordering=date_time')]);
  state.patients = list(patients); state.appointments = list(appointments);
  const today = new Date(); const todayKey = today.toDateString();
  const todayAppointments = state.appointments.filter(item => new Date(item.date_time).toDateString() === todayKey && item.status !== 'cancelled');
  const upcoming = state.appointments.filter(item => new Date(item.date_time) >= today && item.status === 'scheduled').sort((a,b) => new Date(a.date_time) - new Date(b.date_time)).slice(0, 6);
  const outstanding = currencyTotals(state.appointments, item => item.invoice?.balance);
  const completed = state.appointments.filter(item => item.status === 'completed').length;
  const first = state.user.first_name || state.user.username;
  $('#main-content').innerHTML = `
    <div class="hero-row"><div><h1>Welcome back, ${escapeHtml(first)}.</h1><p class="muted">Here’s the pulse of your clinic today.</p></div><div class="date-card">${todayAppointments.length} visit${todayAppointments.length === 1 ? '' : 's'} on today’s schedule</div></div>
    <section class="stats-grid">
      ${statCard('♙', state.patients.length, 'Total patients')}${statCard('□', todayAppointments.length, 'Appointments today')}${statCard('✓', completed, 'Completed visits')}${statCard('$', outstanding, 'Outstanding balance')}
    </section>
    <div class="dashboard-grid">
      <section class="panel"><div class="panel-head"><h3>Coming up</h3><button class="link-btn" data-view-link="appointments">Full schedule →</button></div>${upcoming.length ? upcoming.map(scheduleRow).join('') : emptyInline('No upcoming appointments yet.')}</section>
      <aside class="panel"><div class="panel-head"><h3>Quick actions</h3></div><div class="quick-list">
        ${canManageSchedule() ? '<button class="quick-action" data-action="new-appointment"><span>+</span>Book an appointment</button>' : ''}
        ${canCreatePatients() ? '<button class="quick-action" data-action="new-patient"><span>♙</span>Add a new patient</button>' : ''}
        <button class="quick-action" data-action="upload-xray"><span>◇</span>Upload an X-ray</button>
      </div></aside>
    </div>`;
}

function statCard(icon, value, label) { return `<article class="stat-card"><span class="stat-icon">${icon}</span><strong>${escapeHtml(value)}</strong><small>${label}</small></article>`; }
function scheduleRow(item) {
  const time = dayTime(item.date_time); const patient = item.patient_detail;
  return `<div class="schedule-item"><div class="time-block">${time.time}<small>${time.day}</small></div><div class="schedule-patient"><span class="avatar">${initials(patient?.full_name)}</span><span><strong>${escapeHtml(patient?.full_name)}</strong><small>${escapeHtml(item.chief_complaint || 'Routine visit')} · Dr. ${escapeHtml(fullName(item.dentist_detail))}</small></span></div><span class="${statusClass(item.status)}">${item.status.replace('_',' ')}</span></div>`;
}
function emptyInline(text) { return `<div class="empty-state"><div class="empty-icon">○</div><p>${text}</p></div>`; }

async function renderPatients(search = '') {
  const payload = await request(`/api/patients/?ordering=full_name${search ? `&search=${encodeURIComponent(search)}` : ''}`);
  state.patients = list(payload);
  $('#main-content').innerHTML = `
    <div class="page-head"><div><h1>Patients</h1><p class="muted">Clinical details and contact records in one place.</p></div>${canCreatePatients() ? '<button class="btn btn-primary" data-action="new-patient">+ Add patient</button>' : ''}</div>
    <div class="toolbar"><input class="search" id="patient-search" value="${escapeHtml(search)}" placeholder="Search by name, phone, or email…"><select id="patient-order"><option value="full_name">Name A–Z</option><option value="-created_at">Newest first</option></select></div>
    <div class="table-card">${patientTable(state.patients)}</div>`;
  let timer; $('#patient-search').addEventListener('input', e => { clearTimeout(timer); timer = setTimeout(() => renderPatients(e.target.value.trim()), 300); });
  $('#patient-order').addEventListener('change', async e => { const data = list(await request(`/api/patients/?ordering=${e.target.value}`)); state.patients = data; $('.table-card').innerHTML = patientTable(data); });
}

function patientTable(items) {
  if (!items.length) return emptyInline('No patients match this search.');
  return `<table class="data-table"><thead><tr><th>PATIENT</th><th>CONTACT</th><th>AGE</th><th>BLOOD TYPE</th><th>LAST UPDATED</th><th></th></tr></thead><tbody>${items.map(patient => `<tr><td><div class="person"><span class="avatar">${initials(patient.full_name)}</span><span><strong>${escapeHtml(patient.full_name)}</strong><small>#${patient.id}</small></span></div></td><td>${escapeHtml(patient.phone || '—')}<br><small class="muted">${escapeHtml(patient.email || '')}</small></td><td>${patient.age ?? '—'}</td><td><span class="pill">${escapeHtml(patient.blood_type)}</span></td><td>${dateTime(patient.updated_at)}</td><td><div class="row-actions"><button class="btn btn-secondary btn-sm" data-action="view-patient" data-id="${patient.id}">View</button><button class="btn btn-ghost btn-sm" data-action="edit-patient" data-id="${patient.id}">Edit</button></div></td></tr>`).join('')}</tbody></table>`;
}

function patientForm(patient = {}) {
  if (!patient.id && !canCreatePatients()) return toast('Your role cannot create patient records.', 'error');
  const clinicalDisabled = isReceptionistUser() ? 'disabled' : '';
  const clinicalHelp = isReceptionistUser() ? '<small class="muted">Clinical fields are read-only for reception staff.</small>' : '';
  openModal(`<p class="eyebrow">PATIENT RECORD</p><h2>${patient.id ? 'Edit patient' : 'Add a new patient'}</h2><p class="modal-intro">Keep contact and medical context accurate for the care team.</p>
    <form class="form-grid" id="patient-form" data-id="${patient.id || ''}">
      <label class="full">Full name<input name="full_name" required value="${escapeHtml(patient.full_name || '')}"></label>
      <label>Phone<input name="phone" value="${escapeHtml(patient.phone || '')}" placeholder="+1 555 0123"></label>
      <label>Email<input type="email" name="email" value="${escapeHtml(patient.email || '')}"></label>
      <label>Date of birth<input type="date" name="date_of_birth" value="${patient.date_of_birth || ''}"></label>
      <label>Blood type<select name="blood_type">${['unknown','A+','A-','B+','B-','AB+','AB-','O+','O-'].map(v => `<option ${patient.blood_type === v ? 'selected':''}>${v}</option>`).join('')}</select></label>
      <label class="full">Allergies<textarea name="allergies" ${clinicalDisabled} placeholder="Known allergies, reactions, or none">${escapeHtml(patient.allergies || '')}</textarea>${clinicalHelp}</label>
      <label class="full">Medical notes<textarea name="medical_notes" ${clinicalDisabled} placeholder="Relevant conditions, medication, or context">${escapeHtml(patient.medical_notes || '')}</textarea>${clinicalHelp}</label>
      <p class="form-error full"></p><div class="form-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary" type="submit">${patient.id ? 'Save changes' : 'Add patient'}</button></div>
    </form>`);
  $('#patient-form').addEventListener('submit', savePatient);
}

async function savePatient(event) {
  event.preventDefault(); const form = event.currentTarget; const id = form.dataset.id; const button = form.querySelector('[type=submit]'); button.disabled = true;
  const data = Object.fromEntries(new FormData(form)); if (!data.date_of_birth) data.date_of_birth = null;
  try { await request(id ? `/api/patients/${id}/` : '/api/patients/', {method:id?'PATCH':'POST', body:JSON.stringify(data)}); closeModal(); toast(id ? 'Patient record updated.' : 'Patient added.'); await navigate('patients'); }
  catch (err) { form.querySelector('.form-error').textContent = err.message; button.disabled = false; }
}

async function viewPatient(id) {
  const [patient, appointmentPayload, xrayPayload] = await Promise.all([
    request(`/api/patients/${id}/`),
    request(`/api/appointments/?patient=${id}&ordering=-date_time`),
    request(`/api/xrays/?patient=${id}`),
  ]);
  const appointments = list(appointmentPayload);
  const xrays = list(xrayPayload);
  const canAddXray = !isDentistUser() || appointments.length > 0;
  openModal(`<p class="eyebrow">PATIENT #${patient.id}</p><h2>${escapeHtml(patient.full_name)}</h2><p class="modal-intro">${escapeHtml(patient.phone || 'No phone')} · ${escapeHtml(patient.email || 'No email')}</p>
    <div class="detail-grid"><div class="detail-box"><small>Age</small><strong>${patient.age ?? 'Unknown'}</strong></div><div class="detail-box"><small>Blood type</small><strong>${escapeHtml(patient.blood_type)}</strong></div><div class="detail-box"><small>Allergies</small><strong>${escapeHtml(patient.allergies || 'None recorded')}</strong></div><div class="detail-box"><small>Total visits</small><strong>${appointments.length}</strong></div></div>
    <h3>Medical notes</h3><p class="muted">${escapeHtml(patient.medical_notes || 'No medical notes recorded.')}</p>
    <div class="record-section"><div class="record-section-head"><h3>X-rays <span>${xrays.length}</span></h3>${canAddXray ? `<button class="btn btn-ghost btn-sm" data-action="patient-xray" data-patient-id="${patient.id}">+ Add X-ray</button>` : ''}</div>${xrayGallery(xrays, 'This patient has no X-rays yet.')}</div>
    <div class="form-actions"><button class="btn btn-secondary" data-close-modal>Close</button><button class="btn btn-primary" data-action="edit-patient" data-id="${patient.id}">Edit record</button></div>`);
  await hydrateProtectedImages($('#modal'));
}

async function renderAppointments(status = '') {
  await ensureReferenceData();
  const filterQuery = status === 'emergency'
    ? '&is_emergency_overbook=true'
    : (status ? `&status=${status}` : '');
  const payload = await request(`/api/appointments/?ordering=date_time${filterQuery}`);
  state.appointments = list(payload);
  $('#main-content').innerHTML = `<div class="page-head"><div><h1>${status === 'emergency' ? 'Emergency overbookings' : 'Appointments'}</h1><p class="muted">${status === 'emergency' ? 'Urgent visits intentionally placed into occupied schedules.' : 'Plan visits, update outcomes, and settle invoices.'}</p></div>${canManageSchedule() ? '<button class="btn btn-primary" data-action="new-appointment">+ New appointment</button>' : ''}</div>
    <div class="toolbar"><input class="search" id="appointment-search" placeholder="Search patient, dentist, or complaint…"><select id="appointment-status"><option value="">All appointments</option><option value="emergency" ${status==='emergency'?'selected':''}>Emergency overbookings</option>${['scheduled','completed','cancelled','no_show'].map(v => `<option value="${v}" ${status===v?'selected':''}>${v.replace('_',' ')}</option>`).join('')}</select></div>
    <div class="table-card">${appointmentTable(state.appointments)}</div>`;
  $('#appointment-status').addEventListener('change', e => renderAppointments(e.target.value));
  let timer; $('#appointment-search').addEventListener('input', e => { clearTimeout(timer); timer = setTimeout(async () => { const data = list(await request(`/api/appointments/?search=${encodeURIComponent(e.target.value)}${filterQuery}`)); state.appointments = data; $('.table-card').innerHTML = appointmentTable(data); }, 300); });
}

function appointmentTable(items) {
  if (!items.length) return emptyInline('There are no appointments in this view.');
  return `<table class="data-table"><thead><tr><th>DATE & TIME</th><th>PATIENT</th><th>DENTIST</th><th>STATUS</th><th>INVOICE</th><th></th></tr></thead><tbody>${items.map(item => `<tr><td><strong>${dateTime(item.date_time)}</strong><br><small class="muted">${item.duration_minutes} min · ${escapeHtml(item.chief_complaint || 'Routine visit')}</small></td><td><div class="person"><span class="avatar">${initials(item.patient_detail?.full_name)}</span><span><strong>${escapeHtml(item.patient_detail?.full_name)}</strong>${item.is_emergency_overbook ? `<small class="role-tag">Emergency overbook</small>` : ''}</span></div></td><td>Dr. ${escapeHtml(fullName(item.dentist_detail))}</td><td><span class="${statusClass(item.status)}">${item.status.replace('_',' ')}</span></td><td><span class="${statusClass(item.invoice?.status || 'unpaid')}">${item.invoice?.status || 'unpaid'} · ${currency(item.invoice?.balance, item.invoice?.currency)}</span></td><td><div class="row-actions"><button class="btn btn-secondary btn-sm" data-action="appointment-detail" data-id="${item.id}">Manage</button><button class="btn btn-ghost btn-sm" data-action="invoice" data-id="${item.id}">Invoice</button></div></td></tr>`).join('')}</tbody></table>`;
}

async function renderFinances(filters = null) {
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
  const values = filters || {
    date_from: firstDay.toISOString().slice(0, 10),
    date_to: today.toISOString().slice(0, 10),
    currency: 'USD',
    dentist: '',
  };
  const query = new URLSearchParams(Object.entries(values).filter(([, value]) => value !== ''));
  const report = await request(`/api/appointments/financial-reports/?${query}`);
  const money = value => currency(value, report.filters.currency);
  const dentistRows = report.by_dentist.length
    ? report.by_dentist.map(row => `<tr><td><strong>Dr. ${escapeHtml(row.dentist_name)}</strong></td><td>${money(row.revenue)}</td><td>${money(row.collections)}</td><td>${money(row.refunds)}</td><td>${money(row.net_collections)}</td><td>${money(row.outstanding)}</td></tr>`).join('')
    : '<tr><td colspan="6" class="muted">No dentist activity in this period.</td></tr>';
  const monthRows = report.by_month.length
    ? report.by_month.map(row => `<tr><td><strong>${escapeHtml(row.month)}</strong></td><td>${money(row.revenue)}</td><td>${money(row.collections)}</td><td>${money(row.refunds)}</td><td>${money(row.net_collections)}</td></tr>`).join('')
    : '<tr><td colspan="5" class="muted">No monthly activity in this period.</td></tr>';
  $('#main-content').innerHTML = `<div class="page-head"><div><h1>Financial reports</h1><p class="muted">Production, cash collections, refunds, and receivables remain separate and auditable.</p></div></div>
    <form class="toolbar" id="finance-filter"><label>From<input type="date" name="date_from" value="${report.filters.date_from}" required></label><label>To<input type="date" name="date_to" value="${report.filters.date_to}" required></label><label>Currency<select name="currency"><option value="USD" ${report.filters.currency==='USD'?'selected':''}>USD</option><option value="EGP" ${report.filters.currency==='EGP'?'selected':''}>EGP</option></select></label><label>Dentist<select name="dentist"><option value="">All dentists</option>${report.dentists.map(dentist => `<option value="${dentist.id}" ${Number(report.filters.dentist)===dentist.id?'selected':''}>Dr. ${escapeHtml(dentist.name)}${dentist.is_active ? '' : ' (inactive)'}</option>`).join('')}</select></label><button class="btn btn-primary" type="submit">Apply filters</button></form>
    <section class="stats-grid">${statCard('$', money(report.summary.revenue), 'Completed treatment revenue')}${statCard('↓', money(report.summary.collections), 'Payments received')}${statCard('↩', money(report.summary.refunds), 'Refunds')}${statCard('✓', money(report.summary.net_collections), 'Net collections')}${statCard('…', money(report.summary.outstanding), 'Outstanding balance')}</section>
    <section class="panel"><div class="panel-head"><div><h3>Performance by dentist</h3><small class="muted">Commission is not calculated; these are production and collection figures.</small></div></div><div class="table-card"><table class="data-table"><thead><tr><th>DENTIST</th><th>REVENUE</th><th>COLLECTIONS</th><th>REFUNDS</th><th>NET COLLECTIONS</th><th>OUTSTANDING</th></tr></thead><tbody>${dentistRows}</tbody></table></div></section>
    <section class="panel record-section"><div class="panel-head"><h3>Monthly totals</h3></div><div class="table-card"><table class="data-table"><thead><tr><th>MONTH</th><th>REVENUE</th><th>COLLECTIONS</th><th>REFUNDS</th><th>NET COLLECTIONS</th></tr></thead><tbody>${monthRows}</tbody></table></div></section>`;
  $('#finance-filter').addEventListener('submit', event => {
    event.preventDefault();
    renderFinances(Object.fromEntries(new FormData(event.currentTarget)));
  });
}

async function appointmentForm() {
  if (!canManageSchedule()) return toast('Only administrators and receptionists can schedule appointments.', 'error');
  await ensureReferenceData();
  if (!state.patients.length || !state.dentists.length) return toast('Add at least one patient and dentist before booking.', 'error');
  const min = new Date(Date.now() + 5 * 60000); min.setMinutes(min.getMinutes() - min.getTimezoneOffset());
  openModal(`<p class="eyebrow">NEW VISIT</p><h2>Book an appointment</h2><p class="modal-intro">Choose a patient, clinician, and a future time.</p><form class="form-grid" id="appointment-form">
    <label class="full">Find patient${patientPicker(state.patients, null, 'appointment-patients')}</label>
    <label>Dentist<select name="dentist" required><option value="">Select dentist</option>${state.dentists.map(d => `<option value="${d.id}">Dr. ${escapeHtml(fullName(d))}${d.specialization ? ` · ${escapeHtml(d.specialization)}` : ''}</option>`).join('')}</select></label>
    <label>Date and time<input type="datetime-local" name="date_time" min="${min.toISOString().slice(0,16)}" required></label>
    <label>Duration<select name="duration_minutes"><option value="15">15 minutes</option><option value="30" selected>30 minutes</option><option value="45">45 minutes</option><option value="60">60 minutes</option><option value="90">90 minutes</option><option value="120">120 minutes</option></select></label><label class="check-label"><input type="checkbox" name="is_emergency_overbook"> Emergency overbook</label>
    <label class="full hidden" id="emergency-reason-label">Emergency reason<textarea name="emergency_reason" placeholder="Why must this visit be placed into an occupied schedule?"></textarea></label>
    <label class="full">Chief complaint<input name="chief_complaint" placeholder="What brings the patient in?"></label>
    <label class="full">Notes<textarea name="notes" placeholder="Preparation notes or scheduling context"></textarea></label>
    <p class="form-error full"></p><div class="form-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary" type="submit">Book appointment</button></div></form>`);
  $('#appointment-form').addEventListener('submit', saveAppointment);
  $('#appointment-form [name="is_emergency_overbook"]').addEventListener('change', event => {
    const label = $('#emergency-reason-label');
    label.classList.toggle('hidden', !event.target.checked);
    label.querySelector('textarea').required = event.target.checked;
  });
}

async function saveAppointment(event) {
  event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('[type=submit]'); button.disabled = true;
  const data = Object.fromEntries(new FormData(form));
  data.is_emergency_overbook = form.elements.is_emergency_overbook.checked;
  data.patient = selectedPatientId(form);
  delete data.patient_search;
  if (!data.patient) {
    form.querySelector('.form-error').textContent = 'Choose a patient from the search suggestions.';
    button.disabled = false;
    return;
  }
  data.date_time = new Date(data.date_time).toISOString();
  try { await request('/api/appointments/', {method:'POST', body:JSON.stringify(data)}); closeModal(); toast('Appointment booked.'); await navigate('appointments'); }
  catch(err) { form.querySelector('.form-error').textContent = err.message; button.disabled = false; }
}

async function appointmentDetail(id) {
  const [item, xrayPayload] = await Promise.all([
    request(`/api/appointments/${id}/`),
    request(`/api/xrays/?appointment=${id}`),
  ]);
  const xrays = list(xrayPayload);
  const terminalStatuses = new Set(['completed', 'cancelled', 'no_show']);
  const statusChoices = terminalStatuses.has(item.status)
    ? [item.status]
    : (new Date(item.date_time) <= new Date()
      ? ['scheduled', 'completed', 'cancelled', 'no_show']
      : ['scheduled', 'cancelled']);
  const clinicalFields = canEditClinicalOutcome()
    ? `<label class="full">Diagnosis<textarea name="diagnosis">${escapeHtml(item.diagnosis || '')}</textarea></label><label class="full">Procedures performed<textarea name="procedures_done">${escapeHtml(item.procedures_done || '')}</textarea></label><label class="full">Clinical notes<textarea name="notes">${escapeHtml(item.notes || '')}</textarea></label>`
    : `<div class="detail-box full"><small>Diagnosis</small><strong>${escapeHtml(item.diagnosis || 'Not recorded')}</strong></div><div class="detail-box full"><small>Procedures performed</small><strong>${escapeHtml(item.procedures_done || 'Not recorded')}</strong></div><p class="muted full">Clinical outcomes are read-only for reception staff.</p>`;
  openModal(`<p class="eyebrow">APPOINTMENT #${item.id}</p><h2>${escapeHtml(item.patient_detail.full_name)}</h2><p class="modal-intro">${dateTime(item.date_time)} with Dr. ${escapeHtml(fullName(item.dentist_detail))}</p>
    <div class="detail-grid"><div class="detail-box"><small>Status</small><strong>${item.status.replace('_',' ')}</strong></div><div class="detail-box"><small>Duration</small><strong>${item.duration_minutes} minutes</strong></div><div class="detail-box"><small>Balance</small><strong>${currency(item.invoice?.balance, item.invoice?.currency)}</strong></div>${item.is_emergency_overbook ? `<div class="detail-box"><small>Emergency overbook</small><strong>${escapeHtml(item.emergency_reason)}</strong></div>` : ''}</div>
    <div class="record-section"><div class="record-section-head"><h3>Appointment X-rays <span>${xrays.length}</span></h3><button type="button" class="btn btn-ghost btn-sm" data-action="appointment-xray" data-id="${item.id}" data-patient-id="${item.patient}">+ Add X-ray</button></div>${xrayGallery(xrays, 'No X-rays are attached to this appointment.')}</div>
    <form class="form-grid" id="outcome-form" data-id="${item.id}"><label>Status<select name="status">${statusChoices.map(v => `<option value="${v}" ${item.status===v?'selected':''}>${v.replace('_',' ')}</option>`).join('')}</select></label><span></span>
      ${clinicalFields}
      <p class="form-error full"></p><div class="form-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary" type="submit">Save visit</button></div></form>`);
  await hydrateProtectedImages($('#modal'));
  $('#outcome-form').addEventListener('submit', saveOutcome);
}

async function saveOutcome(event) {
  event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('[type=submit]'); button.disabled = true;
  try { await request(`/api/appointments/${form.dataset.id}/`, {method:'PATCH', body:JSON.stringify(Object.fromEntries(new FormData(form)))}); closeModal(); toast('Visit updated.'); await navigate('appointments'); }
  catch(err) { form.querySelector('.form-error').textContent = err.message; button.disabled = false; }
}

async function invoiceModal(id) {
  const invoice = await request(`/api/appointments/${id}/invoice/`);
  const money = value => currency(value, invoice.currency);
  const hasTransactions = invoice.transactions.length > 0;
  const lineRows = invoice.line_items.length
    ? invoice.line_items.map(item => `<tr><td><strong>${escapeHtml(item.description)}</strong><br><small class="muted">${escapeHtml(item.procedure_code || '')}</small></td><td>${item.quantity}</td><td>${money(item.unit_price)}</td><td>${money(item.total)}</td>${canManageInvoices() && !hasTransactions ? `<td><button class="btn btn-danger btn-sm" data-action="delete-invoice-item" data-id="${item.id}" data-appointment-id="${id}">Remove</button></td>` : ''}</tr>`).join('')
    : `<tr><td colspan="5" class="muted">No treatment charges have been added.</td></tr>`;
  const transactionRows = invoice.transactions.length
    ? invoice.transactions.map(entry => `<tr><td>${dateTime(entry.occurred_at)}</td><td><span class="role-tag">${escapeHtml(entry.transaction_type)}</span></td><td>${escapeHtml(entry.payment_method.replace('_', ' '))}</td><td>${entry.transaction_type === 'refund' ? '−' : '+'}${money(entry.amount)}</td><td>${escapeHtml(entry.reference || '—')}</td></tr>`).join('')
    : `<tr><td colspan="5" class="muted">No payments or refunds recorded.</td></tr>`;
  const now = new Date(); now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  const managerForms = canManageInvoices() ? `
    <div class="record-section"><h3>Invoice settings</h3><form class="form-grid" id="invoice-meta-form" data-id="${id}"><label>Currency<select name="currency" ${invoice.line_items.length || hasTransactions ? 'disabled' : ''}><option value="USD" ${invoice.currency==='USD'?'selected':''}>USD</option><option value="EGP" ${invoice.currency==='EGP'?'selected':''}>EGP</option></select></label><label class="full">Invoice notes<textarea name="notes">${escapeHtml(invoice.notes || '')}</textarea></label><p class="form-error full"></p><div class="form-actions"><button class="btn btn-secondary" type="submit">Save invoice settings</button></div></form></div>
    <div class="record-section"><h3>Add treatment charge</h3><form class="form-grid" id="invoice-item-form" data-id="${id}"><label class="full">Description<input name="description" required placeholder="Consultation, restoration, crown…"></label><label>Procedure code<input name="procedure_code"></label><label>Quantity<input type="number" name="quantity" min="0.01" step="0.01" value="1" required></label><label>Unit price (${invoice.currency})<input type="number" name="unit_price" min="0" step="0.01" required></label><p class="form-error full"></p><div class="form-actions"><button class="btn btn-primary" type="submit">Add charge</button></div></form></div>
    ${invoice.line_items.length && (invoice.appointment_status !== 'cancelled' || Number(invoice.net_paid) > 0) ? `<div class="record-section"><h3>Record payment or refund</h3><form class="form-grid" id="transaction-form" data-id="${id}"><label>Type<select name="transaction_type">${invoice.appointment_status !== 'cancelled' ? '<option value="payment">Payment</option>' : ''}${Number(invoice.net_paid) > 0 ? '<option value="refund">Refund</option>' : ''}</select></label><label>Amount (${invoice.currency})<input type="number" name="amount" min="0.01" step="0.01" required></label><label>Method<select name="payment_method">${['cash','card','insurance','bank_transfer','other'].map(v => `<option value="${v}">${v.replace('_',' ')}</option>`).join('')}</select></label><label>Date and time<input type="datetime-local" name="occurred_at" value="${now.toISOString().slice(0,16)}" required></label><label>Reference<input name="reference" placeholder="Receipt or transfer reference"></label><label class="full">Notes<textarea name="notes"></textarea></label><p class="form-error full"></p><div class="form-actions"><button class="btn btn-primary" type="submit">Record transaction</button></div></form></div>` : ''}` : '<p class="muted">Financial records are read-only for dentists.</p>';
  openModal(`<p class="eyebrow">INVOICE · ${escapeHtml(invoice.currency)}</p><h2>Financial ledger</h2><div class="detail-grid"><div class="detail-box"><small>Treatment total</small><strong>${money(invoice.total)}</strong></div><div class="detail-box"><small>Payments</small><strong>${money(invoice.payments_total)}</strong></div><div class="detail-box"><small>Refunds</small><strong>${money(invoice.refunds_total)}</strong></div><div class="detail-box"><small>Balance due</small><strong>${money(invoice.balance)}</strong></div></div>
    <div class="record-section"><h3>Treatment charges</h3><div class="table-card"><table class="data-table"><thead><tr><th>DESCRIPTION</th><th>QTY</th><th>UNIT PRICE</th><th>TOTAL</th>${canManageInvoices() && !hasTransactions ? '<th></th>' : ''}</tr></thead><tbody>${lineRows}</tbody></table></div></div>
    <div class="record-section"><h3>Payment history</h3><div class="table-card"><table class="data-table"><thead><tr><th>DATE</th><th>TYPE</th><th>METHOD</th><th>AMOUNT</th><th>REFERENCE</th></tr></thead><tbody>${transactionRows}</tbody></table></div></div>${managerForms}<div class="form-actions"><button class="btn btn-secondary" data-close-modal>Close</button></div>`);
  $('#invoice-meta-form')?.addEventListener('submit', saveInvoiceMetadata);
  $('#invoice-item-form')?.addEventListener('submit', saveInvoiceItem);
  $('#transaction-form')?.addEventListener('submit', savePaymentTransaction);
}

async function refreshInvoiceModal(id, message) {
  closeModal(); toast(message); await invoiceModal(id);
}

async function saveInvoiceMetadata(event) {
  event.preventDefault(); const form = event.currentTarget; const data = Object.fromEntries(new FormData(form));
  try { await request(`/api/appointments/${form.dataset.id}/invoice/`, {method:'PATCH', body:JSON.stringify(data)}); await refreshInvoiceModal(form.dataset.id, 'Invoice settings saved.'); }
  catch(err) { form.querySelector('.form-error').textContent = err.message; }
}

async function saveInvoiceItem(event) {
  event.preventDefault(); const form = event.currentTarget;
  try { await request(`/api/appointments/${form.dataset.id}/invoice/items/`, {method:'POST', body:JSON.stringify(Object.fromEntries(new FormData(form)))}); await refreshInvoiceModal(form.dataset.id, 'Treatment charge added.'); }
  catch(err) { form.querySelector('.form-error').textContent = err.message; }
}

async function savePaymentTransaction(event) {
  event.preventDefault(); const form = event.currentTarget; const data = Object.fromEntries(new FormData(form)); data.occurred_at = new Date(data.occurred_at).toISOString();
  try { await request(`/api/appointments/${form.dataset.id}/invoice/transactions/`, {method:'POST', body:JSON.stringify(data)}); await refreshInvoiceModal(form.dataset.id, data.transaction_type === 'refund' ? 'Refund recorded.' : 'Payment recorded.'); }
  catch(err) { form.querySelector('.form-error').textContent = err.message; }
}

async function deleteInvoiceItem(appointmentId, itemId) {
  if (!window.confirm('Remove this treatment charge?')) return;
  try { await request(`/api/appointments/${appointmentId}/invoice/items/${itemId}/`, {method:'DELETE'}); await refreshInvoiceModal(appointmentId, 'Treatment charge removed.'); }
  catch(err) { toast(err.message, 'error'); }
}

async function renderXrays() {
  const payload = await request('/api/xrays/'); state.xrays = list(payload);
  $('#main-content').innerHTML = `<div class="page-head"><div><h1>X-rays</h1><p class="muted">A secure visual history of patient imaging.</p></div><button class="btn btn-primary" data-action="upload-xray">+ Upload X-ray</button></div>
    ${state.xrays.length ? `<div class="cards-grid">${state.xrays.map(xray => {
      const image = xray.image_cloud || xray.image_local;
      const deleteButton = canDeleteXrays() ? `<button class="btn btn-danger btn-sm xray-delete" data-action="delete-xray" data-id="${xray.id}">Delete X-ray</button>` : '';
      return `<article class="xray-card"><button class="xray-preview" data-action="view-xray" data-id="${xray.id}" ${image ? `data-url="${escapeHtml(image)}"` : ''} data-description="${escapeHtml(xray.description || 'Dental X-ray')}">${image ? `<img data-protected-src="${escapeHtml(image)}" alt="${escapeHtml(xray.description || 'Dental X-ray')}">` : '◇'}<span class="preview-hint">Open image</span></button><div class="xray-body"><p class="eyebrow">${escapeHtml(xray.source)} · ${escapeHtml(xray.storage_type)}</p><h3>${escapeHtml(xray.description || 'Dental X-ray')}</h3><p class="xray-meta">Patient #${xray.patient} · ${dateTime(xray.taken_at || xray.imported_at)}</p>${deleteButton}</div></article>`;
    }).join('')}</div>` : emptyInline('No X-rays have been uploaded yet.')}`;
  await hydrateProtectedImages($('#main-content'));
}

async function viewXrayImage(action) {
  const protectedUrl = action.dataset.url;
  if (!protectedUrl) return toast('This X-ray has no image file.', 'error');
  let url;
  try { url = await protectedImageUrl(protectedUrl); }
  catch(err) { return toast(err.message, 'error'); }
  openModal(`<p class="eyebrow">X-RAY IMAGE</p><h2>${escapeHtml(action.dataset.description || 'Dental X-ray')}</h2><div class="full-xray"><img src="${escapeHtml(url)}" alt="${escapeHtml(action.dataset.description || 'Dental X-ray')}"></div><div class="form-actions"><button class="btn btn-secondary" data-close-modal>Close</button><a class="btn btn-primary" href="${escapeHtml(url)}" target="_blank" rel="noopener">Open original</a></div>`);
}

async function deleteXray(id) {
  if (!window.confirm('Delete this X-ray record and its local image? This cannot be undone.')) return;
  try {
    await request(`/api/xrays/${id}/`, {method:'DELETE'});
    clearProtectedImages();
    if ($('#modal').open) closeModal();
    toast('X-ray deleted.');
    await renderXrays();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function xrayForm(patientId = null, appointmentId = null) {
  if (!state.patients.length) state.patients = list(await request('/api/patients/?ordering=full_name'));
  let eligiblePatients = state.patients;
  if (isDentistUser()) {
    const assignedAppointments = list(await request('/api/appointments/'));
    const assignedPatientIds = new Set(assignedAppointments.map(item => item.patient));
    eligiblePatients = state.patients.filter(patient => assignedPatientIds.has(patient.id));
  }
  if (!eligiblePatients.length) return toast('No eligible patient is assigned to your account.', 'error');
  if (patientId && !eligiblePatients.some(patient => patient.id === Number(patientId))) return toast('This patient is not assigned to you.', 'error');
  if ($('#modal').open) closeModal();
  openModal(`<p class="eyebrow">DIAGNOSTIC IMAGING</p><h2>Upload an X-ray</h2><p class="modal-intro">Images are stored locally unless cloud upload is explicitly enabled by your administrator.</p><form class="form-grid" id="xray-form" data-allowed-patient-ids="${eligiblePatients.map(patient => patient.id).join(',')}">
    <label class="full">Find patient${patientPicker(eligiblePatients, patientId, 'xray-patients')}</label>${appointmentId ? `<input type="hidden" name="appointment" value="${appointmentId}">` : ''}
    <label class="full">Image<input type="file" name="image_file" accept="image/*" required></label><label>Taken at<input type="datetime-local" name="taken_at"></label><span></span><label class="full">Description<textarea name="description" placeholder="View, region, or clinical context"></textarea></label>
    <p class="form-error full"></p><div class="form-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary" type="submit">Upload X-ray</button></div></form>`);
  $('#xray-form').addEventListener('submit', saveXray);
}

async function saveXray(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (form.dataset.submitting === 'true') return;
  const button = form.querySelector('[type="submit"]');
  const data = new FormData(form);
  const patientId = selectedPatientId(form);
  const allowedPatientIds = new Set((form.dataset.allowedPatientIds || '').split(',').filter(Boolean).map(Number));
  if (!patientId || !allowedPatientIds.has(patientId)) {
    form.querySelector('.form-error').textContent = 'Choose a patient from the search suggestions.';
    return;
  }
  data.delete('patient_search');
  data.set('patient', patientId);
  if (data.get('taken_at')) data.set('taken_at', new Date(data.get('taken_at')).toISOString()); else data.delete('taken_at');
  form.dataset.submitting = 'true';
  button.disabled = true;
  button.textContent = 'Uploading…';
  try {
    await request('/api/xrays/', {method:'POST', body:data});
    closeModal();
    toast('X-ray uploaded securely.');
    await navigate('xrays');
  } catch(err) {
    form.dataset.submitting = 'false';
    button.disabled = false;
    button.textContent = 'Upload X-ray';
    form.querySelector('.form-error').textContent = err.message;
  }
}

async function renderTeam() {
  state.staff = list(await request('/api/accounts/staff/'));
  $('#main-content').innerHTML = `<div class="page-head"><div><h1>Team</h1><p class="muted">The people keeping your clinic moving.</p></div><div class="row-actions"><button class="btn btn-secondary" data-action="change-password">Change password</button>${isAdminUser() ? '<button class="btn btn-primary" data-action="new-staff">+ Add staff</button>' : ''}</div></div>
    <div class="cards-grid">${state.staff.map(person => `<article class="team-card"><span class="avatar">${initials(fullName(person))}</span><div><span class="role-tag">${escapeHtml(person.is_active ? person.role : 'inactive')}</span><h3>${escapeHtml(fullName(person))}</h3><p>${escapeHtml(person.specialization || 'Clinic operations')}</p>${isAdminUser() && person.id !== state.user.id ? `<button class="btn btn-ghost btn-sm" data-action="toggle-staff-status" data-id="${person.id}" data-active="${person.is_active}">${person.is_active ? 'Deactivate' : 'Reactivate'}</button>` : ''}</div></article>`).join('')}</div>`;
}

function passwordForm() {
  openModal(`<p class="eyebrow">ACCOUNT SECURITY</p><h2>Change your password</h2><p class="modal-intro">Use a unique password you do not use for another account.</p><form class="form-grid" id="password-form" autocomplete="off">
    <label class="full">Current password<input type="password" name="old_password" autocomplete="current-password" required></label><label class="full">New password<input type="password" name="new_password" minlength="8" autocomplete="new-password" required></label><label class="full">Confirm new password<input type="password" name="confirm_password" minlength="8" autocomplete="new-password" required></label>
    <p class="form-error full"></p><div class="form-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary" type="submit">Change password</button></div></form>`);
  $('#password-form').addEventListener('submit', savePassword);
}

async function savePassword(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  if (data.new_password !== data.confirm_password) {
    form.querySelector('.form-error').textContent = 'The new passwords do not match.';
    return;
  }
  delete data.confirm_password;
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    await request('/api/accounts/password/change/', {method:'POST', body:JSON.stringify(data)});
    closeModal();
    logout();
    toast('Password changed. Sign in again with your new password.');
  } catch(err) {
    button.disabled = false;
    form.querySelector('.form-error').textContent = err.message;
  }
}

async function toggleStaffStatus(id, currentlyActive) {
  if (!isAdminUser()) return toast('Only clinic administrators can manage staff accounts.', 'error');
  const action = currentlyActive ? 'deactivate' : 'reactivate';
  if (!window.confirm(`Are you sure you want to ${action} this staff account?`)) return;
  try {
    await request(`/api/accounts/staff/${id}/status/`, {method:'PATCH', body:JSON.stringify({is_active:!currentlyActive})});
    toast(`Staff account ${currentlyActive ? 'deactivated' : 'reactivated'}.`);
    await renderTeam();
  } catch(err) { toast(err.message, 'error'); }
}

function staffForm() {
  if (!isAdminUser()) return toast('Only clinic administrators can create staff accounts.', 'error');
  openModal(`<p class="eyebrow">ADMINISTRATION</p><h2>Add a staff member</h2><p class="modal-intro">Create secure access for a member of your clinic.</p><form class="form-grid" id="staff-form" autocomplete="off">
    <label>First name<input name="first_name" autocomplete="off"></label><label>Last name<input name="last_name" autocomplete="off"></label><label>Username<input name="username" autocomplete="off" required></label><label>Email<input type="email" name="email" autocomplete="off"></label><label>Role<select name="role"><option value="receptionist">Receptionist</option><option value="dentist">Dentist</option><option value="admin">Admin</option></select></label><label>Phone<input name="phone" autocomplete="off"></label><label class="full">Specialization<input name="specialization" autocomplete="off"></label><label class="full">New password<input type="password" name="password" minlength="8" autocomplete="new-password" placeholder="Create a unique temporary password" value="" required></label>
    <p class="form-error full"></p><div class="form-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary" type="submit">Create account</button></div></form>`);
  $('#staff-form').addEventListener('submit', async event => { event.preventDefault(); try { await request('/api/accounts/register/', {method:'POST', body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))}); closeModal(); toast('Staff account created.'); await navigate('team'); } catch(err) { event.currentTarget.querySelector('.form-error').textContent = err.message; } });
}

function closeSidebar() { $('#sidebar').classList.remove('open'); $('#scrim').classList.remove('open'); }

document.addEventListener('DOMContentLoaded', () => {
  $('#login-form').addEventListener('submit', login);
  $('#logout-btn').addEventListener('click', logout);
  $('#quick-add').addEventListener('click', appointmentForm);
  $('#menu-btn').addEventListener('click', () => { $('#sidebar').classList.add('open'); $('#scrim').classList.add('open'); });
  $('#scrim').addEventListener('click', closeSidebar);
  window.addEventListener('popstate', () => navigate(viewFromPath(), false));
  $('#modal').addEventListener('click', event => { if (event.target === $('#modal')) closeModal(); });
  document.addEventListener('click', event => {
    const close = event.target.closest('[data-close-modal]'); if (close) return closeModal();
    const nav = event.target.closest('[data-view], [data-view-link]'); if (nav) return navigate(nav.dataset.view || nav.dataset.viewLink);
    const action = event.target.closest('[data-action]'); if (!action) return;
    const id = Number(action.dataset.id);
    const patientId = Number(action.dataset.patientId);
    const appointmentId = Number(action.dataset.appointmentId);
    const actions = {retry:()=>navigate(state.view),'new-patient':()=>patientForm(),'edit-patient':()=>patientForm(state.patients.find(p=>p.id===id) || {}),'view-patient':()=>viewPatient(id),'new-appointment':appointmentForm,'appointment-detail':()=>appointmentDetail(id),invoice:()=>invoiceModal(id),'delete-invoice-item':()=>deleteInvoiceItem(appointmentId,id),'upload-xray':()=>xrayForm(),'patient-xray':()=>xrayForm(patientId),'appointment-xray':()=>xrayForm(patientId,id),'view-xray':()=>viewXrayImage(action),'delete-xray':()=>deleteXray(id),'new-staff':staffForm,'change-password':passwordForm,'toggle-staff-status':()=>toggleStaffStatus(id, action.dataset.active === 'true')};
    actions[action.dataset.action]?.();
  });
  boot();
});
