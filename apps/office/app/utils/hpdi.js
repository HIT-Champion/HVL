// Copyright 2026 Signet Team
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0

// Tự chẩn đoán mức trưởng thành H-P-D-I (trang /tu-chan-doan, docs/tu-chan-doan.md). Bộ câu nằm ở
// app/data/tu-chan-doan.json (schema cùng thư mục); tệp này chỉ có phép tính, không có chữ hiển thị.
// - Điểm mỗi không gian = trung bình mức (1–5) các câu đã trả lời, làm tròn 2 chữ số. CSDL tính lại đúng cách này khi
//   lưu (trigger maturity_assessments_guard, migration 1792281603100): người gửi không chọn được điểm.
// - Lệch nền: theo nguyên lý tiến hóa tuyến tính H → P → D → I (bài giới thiệu chủ đề 761), không gian sau cao hơn
//   không gian ngay trước từ 1 mức trở lên — vd [I] dựng trên [D] chưa vững là "rác vào, rác ra".
// - Nên làm trước: điểm thấp nhất trong các không gian từ [H] tới trước chỗ lệch nền đầu tiên (không lệch thì cả bốn),
//   bằng nhau lấy không gian đứng trước; cả bốn đạt 5 thì không có.
// - Bằng chứng đo được: chỉ số tính từ các khung nhìn số đếm đã có (F3.11, F4.1, F4.3, F4.6) và hồ sơ (F3.8). Chưa có
//   dữ liệu (mẫu số 0, không có dòng) thì không trả chỉ số — trang không hiện, không ghi 0 %. Không quy số đo ra mức:
//   số chỉ đặt cạnh câu tự đánh giá để lãnh đạo đối chiếu.



export const HPDI_KEYS = ['h', 'p', 'd', 'i'];

export const HPDI_TOP = 5;
export const HPDI_GAP = 1; // chênh từ một mức trở lên mới là lệch nền

















export function hpdiText(text, locale) {
  return locale === 'en' ? text.en : text.vi;
}

// Ai dùng trang: lãnh đạo đơn vị, lãnh đạo phòng trả lời, xem kết quả; chỉ lãnh đạo đơn vị lưu, xem bằng chứng và
// lịch sử (các view số đo, bảng lưu chỉ cấp quyền cho director)
export function hpdiAccess(role) {
  return { open: role === 'director' || role === 'manager', leader: role === 'director' };
}

// Liên kết "bước tiếp theo" là liên kết thật chỉ khi người xem mở được trang đích: roles của liên kết chép đúng điều
// kiện vai trò của mục menu trang đó (layouts/default.vue, test đối chiếu); không khai roles là trang mọi vai trò dùng
// trang này đều mở được. Không mở được thì trang hiện tên trang và vai trò làm việc đó, không dẫn tới.
export function hpdiLinkOpen(link, role) {
  return !!role && (!link.roles || link.roles.includes(role));
}

function isLevel(v) {
  return typeof v === 'number' && Number.isInteger(v) && v >= 1 && v <= HPDI_TOP;
}

const round2 = (x) => Math.round(x * 100) / 100;

export function hpdiQuestions(f) {
  return f.spaces.flatMap((s) => s.questions);
}

// Chỉ giữ câu có trong bộ câu và mức hợp lệ: bản dở trong trình duyệt, "điền theo lần trước" (lần lưu có thể theo bộ
// câu cũ hơn) đi qua đây trước khi vào form
export function hpdiCleanAnswers(f, raw) {
  const out = {};
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return out;
  for (const q of hpdiQuestions(f)) {
    const v = raw[q.id];
    if (isLevel(v)) out[q.id] = v;
  }
  return out;
}

// Đúng ba trường lãnh đạo đơn vị được gửi khi lưu (metadata office_maturity_assessments.yaml): phiên bản bộ câu, câu
// trả lời đã lọc theo bộ câu, ghi chú đã gọt (trống thì null). Thuê ước, người lưu, điểm, giờ lưu do Hasura, CSDL đặt.
export function hpdiSaveInput(f, answers, note) {
  return { framework: f.id, answers: hpdiCleanAnswers(f, answers), note: note.trim() || null };
}

export function hpdiAnswered(f, answers) {
  return hpdiQuestions(f).filter((q) => isLevel(answers[q.id])).length;
}

export function hpdiComplete(f, answers) {
  return hpdiAnswered(f, answers) === hpdiQuestions(f).length;
}

export function hpdiScores(f, answers) {
  const scores = { h: null, p: null, d: null, i: null };
  for (const s of f.spaces) {
    const levels = s.questions.map((q) => answers[q.id]).filter(isLevel);
    scores[s.key] = levels.length ? round2(levels.reduce((a, b) => a + b, 0) / levels.length) : null;
  }
  return scores;
}



// Cặp liền kề H→P, P→D, D→I mà không gian sau vượt không gian trước từ HPDI_GAP mức trở lên
export function hpdiGaps(scores) {
  const gaps = [];
  for (let k = 1; k < HPDI_KEYS.length; k++) {
    const from = HPDI_KEYS[k - 1];
    const to = HPDI_KEYS[k];
    const a = scores[from];
    const b = scores[to];
    if (a === null || b === null) continue;
    const diff = round2(b - a);
    if (diff >= HPDI_GAP) gaps.push({ from, to, diff });
  }
  return gaps;
}

export function hpdiFocus(scores) {
  const gaps = hpdiGaps(scores);
  const last = gaps.length ? HPDI_KEYS.indexOf(gaps[0].from) : HPDI_KEYS.length - 1;
  let best = null;
  for (const key of HPDI_KEYS.slice(0, last + 1)) {
    const s = scores[key];
    if (s === null || s >= HPDI_TOP) continue;
    if (best === null || s < scores[best]) best = key;
  }
  return best;
}



// Bước tiếp theo của mỗi không gian: câu có mức thấp nhất (dưới 5), bằng nhau lấy câu đứng trước
export function hpdiNextSteps(f, answers) {
  const steps = [];
  for (const s of f.spaces) {
    let pick = null;
    for (const q of s.questions) {
      const level = answers[q.id];
      if (!isLevel(level) || level >= HPDI_TOP) continue;
      if (pick === null || level < pick.level) pick = { space: s.key, question: q, level };
    }
    if (pick) steps.push(pick);
  }
  return steps;
}

// Thứ tự trục trên radar: [H], [P], [D], [I]; chưa có điểm thì vẽ ở tâm
export function hpdiRadarValues(scores) {
  return HPDI_KEYS.map((k) => scores[k] ?? 0);
}

// --- Hình dạng H-P-D-I và cảnh báo GIGO -----------------------------------------------------------------------------
// Theo giáo trình "Xây dựng Hệ điều hành Doanh nghiệp số (DX-OS)" của TS. Tạ Tuấn Anh (CC BY 4.0), mục 2.4 "Phương
// pháp luận: Thuật toán Ánh xạ và Dashboard HPDI" (đường dẫn trong nguồn của bộ câu, app/data/tu-chan-doan.json; đọc
// ngày 25/10/2026). Đội tự viết lại từ lời giáo trình; không lấy mã hay ngưỡng của dự án nào khác.
// - 2.4.2: P% = (điểm đạt / điểm tối đa) × hệ số thực chứng × 30 %, D%, I% như vậy; H% = 100 % − (P% + D% + I%), phần
//   việc còn lại trên vai con người. Ở đây "điểm đạt / tối đa" là (mức − 1) / 4 (mức 1 → 0 %, mức 5 → 30 %); hệ số
//   thực chứng lấy bằng 1 vì mỗi mức của bộ câu đã tả việc quan sát được, không tả phần mềm sở hữu — bằng chứng đo
//   được đặt cạnh để đối chiếu, không nhân vào. Điểm không gian [H] của bộ câu (không gian làm việc số) không vào
//   công thức: H% của giáo trình là phần dư, không phải mức của không gian [H].
// - 2.4.3: bốn nguyên mẫu trên radar tỷ trọng. Ngưỡng dưới lấy từ số giáo trình ghi; chỗ giáo trình chỉ tả bằng lời
//   ("co cụm sát tâm", "triệt tiêu", "vươn dài") thì lấy một phần ba trục (10 %), ghi rõ ở từng luật.
export const HPDI_SHARE_MAX = 30;


export const HPDI_SHAPES = ['diamond', 'illusion', 'kite', 'spear', 'transitional'];

const round1 = (x) => Math.round(x * 10) / 10;

// Tỷ trọng % theo 2.4.2; thiếu điểm [P], [D] hay [I] thì không tính
export function hpdiShares(scores) {
  const { p, d, i } = scores;
  if (p === null || d === null || i === null) return null;
  const share = (s) => round1((s - 1) / (HPDI_TOP - 1) * HPDI_SHARE_MAX);
  const out = { p: share(p), d: share(d), i: share(i) };
  return { h: round1(100 - out.p - out.d - out.i), ...out };
}

// Xét theo thứ tự, luật đầu tiên khớp là hình dạng:
// 1. Kim cương toàn vẹn — "[P], [D], [I] mở rộng đối xứng, đạt đỉnh 30 % mỗi trục", [H] về 10 %: cả ba từ 22,5 %
//    (ba phần tư trục, mức 4) trở lên.
// 2. Ảo giác công nghệ — "trục [I] hoặc [D] vươn dài … đi kèm sự suy giảm của trục [P]", hậu quả GIGO: [D] hoặc [I]
//    từ 10 % trở lên, vượt [P], và [P] chưa tới 20 % (dải [P] của Cánh diều).
// 3. Cánh diều lệch tâm — "[P] vươn dài … (20 % – 30 %). Trục [D] và [I] vẫn ở trạng thái triệt tiêu": [P] từ 20 %,
//    [D] và [I] dưới 10 %.
// 4. Mũi giáo phân mảnh — "[H] (chiếm 80 % – 90 %)": H% từ 80 % trở lên.
// 5. Không khớp nguyên mẫu nào: đang chuyển tiếp (giáo trình chỉ tả bốn nguyên mẫu "phổ biến").
export function hpdiShape(s) {
  const third = HPDI_SHARE_MAX / 3;
  if (s.p >= 22.5 && s.d >= 22.5 && s.i >= 22.5) return 'diamond';
  if (Math.max(s.d, s.i) >= third && Math.max(s.d, s.i) > s.p && s.p < 20) return 'illusion';
  if (s.p >= 20 && s.d < third && s.i < third) return 'kite';
  if (s.h >= 80) return 'spear';
  return 'transitional';
}

// Rác vào, rác ra: [I] dựng trên [D] chưa vững (lệch nền D → I) hoặc hình dạng Ảo giác công nghệ. Trang khuyên tạm
// dừng mở rộng [I], chuẩn hóa [P], [D] trước, và trỏ tới cờ kiểm chất lượng số liệu của các báo cáo (Phả hệ số liệu)
export function hpdiGigo(scores, shape) {
  if (shape === 'illusion') return true;
  return hpdiGaps(scores).some((g) => g.from === 'd' && g.to === 'i');
}

// Nơi xem cờ chất lượng: mục "Kiểm chất lượng số liệu" của trang Phả hệ số liệu — cùng điều kiện vai trò với mục
// /pha-he của thanh bên (test đối chiếu)
export const HPDI_QUALITY_LINK = {
  to: '/pha-he',
  roles: ['director'],
  label: { vi: 'Phả hệ số liệu — kiểm chất lượng số liệu', en: 'Data lineage — data quality checks' }
};

// --- Lịch sử (bảng office.maturity_assessments) ---------------------------------------------------------------------













// Cột numeric: Hasura có thể trả số hoặc chuỗi tùy cấu hình, đọc cả hai
export function hpdiRowScores(row) {
  const num = (v) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  return { h: num(row.h), p: num(row.p), d: num(row.d), i: num(row.i) };
}

// --- Bằng chứng đo được --------------------------------------------------------------------------------------------



















// Mã chỉ số theo không gian, đúng thứ tự hiện trên trang (khóa i18n hpdi.evidence.<mã>)
export const HPDI_EVIDENCE = {
  h: ['feedback'],
  p: ['overdueNow', 'overdueRate', 'timeToAssign'],
  d: ['documents', 'archivedDocuments', 'caseFiles'],
  i: ['intakeKept', 'suggestionKept']
};

const sum = (rows, pick) => rows.reduce((n, r) => n + pick(r), 0);

export function hpdiEvidence(data) {
  const out = [];
  const add = (space, id, values) => out.push({ space, id, values });

  const feedback = data.feedback.find((r) => r.screen === null);
  if (feedback && feedback.feedback > 0) {
    add('h', 'feedback', { avg: feedback.rating_total / feedback.feedback, n: feedback.feedback });
  }

  // Không tính văn bản đã hủy; văn bản hạn chế không lộ trạng thái (status null) nên chỉ vào tổng số văn bản
  const live = data.counts.filter((r) => r.status !== 'cancelled');
  const open = live.filter((r) => !r.restricted);
  const incoming = open.filter((r) => r.direction === 'in');
  if (incoming.length) {
    add('p', 'overdueNow', { n: sum(incoming.filter((r) => r.overdue === true), (r) => r.documents) });
  }
  const late = data.overdue.find((r) => r.month === null);
  if (late && late.judged > 0) {
    add('p', 'overdueRate', { pct: late.late / late.judged * 100, late: late.late, n: late.judged });
  }
  const assign = data.assign.find((r) => r.month === null);
  if (assign && assign.assigned > 0 && assign.median_hours !== null) {
    add('p', 'timeToAssign', { hours: assign.median_hours, n: assign.assigned });
  }

  const documents = sum(live, (r) => r.documents);
  if (documents > 0) {
    const by = (direction) => sum(live.filter((r) => r.direction === direction), (r) => r.documents);
    add('d', 'documents', { n: documents, incoming: by('in'), outgoing: by('out') });
    add('d', 'archivedDocuments', { n: sum(open.filter((r) => r.status === 'archived'), (r) => r.documents) });
  }
  if (data.caseFiles.length) {
    add('d', 'caseFiles', { archived: data.caseFiles.filter((r) => r.status === 'archived').length,
      n: data.caseFiles.length });
  }

  const suggested = sum(data.intake, (r) => r.suggested);
  if (suggested > 0) {
    const kept = sum(data.intake, (r) => r.kept);
    add('i', 'intakeKept', { pct: kept / suggested * 100, kept, n: suggested });
  }
  const decided = sum(data.suggestions, (r) => r.decided);
  if (decided > 0) {
    const kept = sum(data.suggestions, (r) => r.kept_unit);
    add('i', 'suggestionKept', { pct: kept / decided * 100, kept, n: decided });
  }
  return out;
}

// Số tính trên đơn vị mẫu của make seed (cột sample của các view F4.6)
export function hpdiSample(data) {
  return [data.assign, data.overdue, data.feedback].some((rows) => rows.some((r) => r.sample));
}
