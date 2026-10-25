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

// Vân tay SHA-256 của hai tệp PEM công khai ở cổng xác thực: chứng thư CA nội bộ (/api/verify/ca.pem, chỉ minh họa) và
// khóa công khai ký mốc neo sổ kiểm toán (/api/verify/anchor-key.pem). Trình duyệt tự tính trên đúng tệp vừa tải (Web
// Crypto, cần HTTPS); người dùng so với kết quả OpenSSL trên máy mình hoặc với nơi công bố khác (kho mốc công khai).
// Dạng hiện ra theo đúng lệnh trong docs/van-hanh.md mục "Mốc neo công khai":
//   ca      `openssl x509 -in signet-ca.pem -noout -fingerprint -sha256` → AB:CD:…:EF (SHA-256 của DER chứng thư)
//   anchor  `openssl pkey -pubin -in anchor-key.pem -outform DER | sha256sum` → sha256:<hex>, như trường "key" của
//           mỗi dòng mốc trong anchors.jsonl



/** DER của khối PEM đầu tiên (CERTIFICATE, PUBLIC KEY…); không đọc được thì null. */
export function pemToDer(pem) {
  const block = /-----BEGIN ([A-Z0-9 ]+)-----([\s\S]*?)-----END \1-----/.exec(pem);
  if (!block) return null;
  let binary;
  try {
    binary = atob(block[2].replace(/\s+/g, ''));
  } catch {
    return null;
  }
  if (!binary) return null;
  const der = new ArrayBuffer(binary.length);
  const view = new Uint8Array(der);
  for (let i = 0; i < binary.length; i++) view[i] = binary.charCodeAt(i);
  return der;
}

/** Vân tay SHA-256 của tệp PEM theo dạng của lệnh OpenSSL tương ứng; trình duyệt không tính được (không HTTPS) hoặc
 * tệp không phải PEM thì null. */
export async function pemFingerprint(pem, style) {
  const der = pemToDer(pem);
  if (!der || !globalThis.crypto?.subtle) return null;
  const digest = new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', der));
  const bytes = Array.from(digest, (b) => b.toString(16).padStart(2, '0'));
  return style === 'anchor' ? `sha256:${bytes.join('')}` : bytes.join(':').toUpperCase();
}
