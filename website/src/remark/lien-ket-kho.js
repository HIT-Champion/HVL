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

// Tài liệu viết để đọc trên GitHub nên có liên kết tương đối tới tệp mã, thư mục (`../services/svc-files/`,
// `../LICENSE`) và tới tệp .md không đưa lên trang. Trên trang tài liệu các đích đó không có trang, Docusaurus báo
// liên kết hỏng. Plugin chạy trước bước Docusaurus phân giải liên kết .md:
// - thư mục có README được đưa lên: trỏ tới README đó;
// - tệp, thư mục còn lại: đổi thành liên kết GitHub trên nhánh đang đăng;
// - đích không tồn tại: để nguyên cho Docusaurus báo lỗi (onBrokenMarkdownLinks).
// Ảnh không đụng tới, Docusaurus tự đóng gói.

import fs from 'node:fs';
import path from 'node:path';
import {createMatcher} from '@docusaurus/utils';

const CO_GIAO_THUC = /^[a-z][a-z\d+.-]*:/i;

/** Bộ lọc "tệp này có lên trang không", cùng mẫu include, exclude với cấu hình docs; đường dẫn tính từ gốc repo. */
export function taoBoLoc(goc, include, exclude) {
  const co = createMatcher(include);
  const bo = createMatcher(exclude);
  return (rel) => co(rel) && !bo(rel) && fs.statSync(path.join(goc, rel), {throwIfNoEntry: false})?.isFile() === true;
}

function duyet(nut, lam) {
  lam(nut);
  for (const con of nut.children ?? []) duyet(con, lam);
}

/** Đường dẫn kiểu POSIX từ thư mục `tu` tới `toi` (cả hai tuyệt đối). */
function tuongDoi(tu, toi) {
  return path.relative(tu, toi).split(path.sep).join('/');
}

export default function lienKetKho({goc, dangLen, kho, nhanh}) {
  return (cay, tep) => {
    const thuMuc = path.dirname(tep.path);
    duyet(cay, (nut) => {
      if ((nut.type !== 'link' && nut.type !== 'definition') || !nut.url) return;
      const url = nut.url;
      if (CO_GIAO_THUC.test(url) || url.startsWith('/') || url.startsWith('#')) return;
      const cat = url.search(/[?#]/);
      const duongDan = cat < 0 ? url : url.slice(0, cat);
      const duoi = cat < 0 ? '' : url.slice(cat);
      let dich;
      try {
        dich = path.resolve(thuMuc, decodeURIComponent(duongDan));
      } catch {
        return;
      }
      const rel = tuongDoi(goc, dich);
      if (rel.startsWith('..') || dangLen(rel)) return;
      const loai = fs.statSync(dich, {throwIfNoEntry: false});
      if (!loai) return;
      if (loai.isDirectory()) {
        const readme = rel ? `${rel}/README.md` : 'README.md';
        nut.url = dangLen(readme)
          ? tuongDoi(thuMuc, path.join(goc, readme)) + duoi
          : `${kho}/tree/${nhanh}/${rel}${duoi}`;
      } else {
        nut.url = `${kho}/blob/${nhanh}/${rel}${duoi}`;
      }
    });
  };
}
