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


// Vân tay SHA-256 trang /xac-thuc hiện cho chứng thư CA và khóa công khai ký mốc neo: trùng từng ký tự với kết quả của
// OpenSSL (giá trị dưới đây chép từ OpenSSL 3.0.13) và với trường "key" mà svc-files ghi vào mỗi dòng mốc
// (services/svc-files/tests/test_anchors.py dùng cùng khóa); tệp không phải PEM thì không bịa vân tay.

import assert from 'node:assert/strict'
import { test } from 'node:test'

const { pemFingerprint, pemToDer } = await import('../app/utils/pemFingerprint.ts')

// khóa công khai của RFC 8032 §7.1 TEST 1, dạng SubjectPublicKeyInfo
const ANCHOR_KEY = `-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=
-----END PUBLIC KEY-----
`
// chứng thư tự ký nhỏ (Ed25519) cho test; `openssl x509 -noout -fingerprint -sha256` in vân tay ở CA_FINGERPRINT
const CA = `-----BEGIN CERTIFICATE-----
MIIBdTCCASegAwIBAgIUIElYfZWNjZ3yDNeKDMtkC4/IlSIwBQYDK2VwMDAxGDAW
BgNVBAMMD0NBIHRodSAtIFNpZ25ldDEUMBIGA1UECgwLU2lnbmV0IHRlc3QwHhcN
MjYxMDI1MDk1NzEyWhcNMzYxMDIyMDk1NzEyWjAwMRgwFgYDVQQDDA9DQSB0aHUg
LSBTaWduZXQxFDASBgNVBAoMC1NpZ25ldCB0ZXN0MCowBQYDK2VwAyEAN3/QEjqp
3pomdR9HOMwWQ3yFDtcPhkK17BT39dudb4ijUzBRMB0GA1UdDgQWBBQi6FeZTnQX
JV+BVuEQtk81w/MR/zAfBgNVHSMEGDAWgBQi6FeZTnQXJV+BVuEQtk81w/MR/zAP
BgNVHRMBAf8EBTADAQH/MAUGAytlcANBAE8KfXAe8mfrQzDU6nMdflPbkt9p0eUq
Ay7NjLFFLcEzTtHdT2X5NIq8iHqw+uljC67OS9LgoMf/cWfzQ2eQqgY=
-----END CERTIFICATE-----
`
const CA_FINGERPRINT = 'F3:90:FB:A5:14:E4:70:C7:81:0A:72:99:94:53:73:38:31:8A:C3:33:56:C6:C4:69:77:4E:39:94:CB:EA:42:22'

test('khóa ký mốc neo: sha256:<hex> của DER, như `openssl pkey -pubin -outform DER | sha256sum`', async () => {
  assert.equal(await pemFingerprint(ANCHOR_KEY, 'anchor'),
    'sha256:06e3fd8fda29bb60ab59557de61edb0aecdb231134be30e75b455f8e1b792fa9')
  assert.equal(new Uint8Array(pemToDer(ANCHOR_KEY)!).length, 44)       // 12 byte tiền tố SPKI + 32 byte khóa
})

test('chứng thư CA: AB:CD:… như `openssl x509 -noout -fingerprint -sha256`', async () => {
  assert.equal(await pemFingerprint(CA, 'ca'), CA_FINGERPRINT)
  // dòng trắng, CRLF trong tệp tải về không đổi vân tay
  assert.equal(await pemFingerprint(`\r\n${CA.replace(/\n/g, '\r\n')}`, 'ca'), CA_FINGERPRINT)
})

test('không phải PEM, base64 hỏng, khối rỗng: null', async () => {
  for (const text of ['', 'not a pem', '-----BEGIN PUBLIC KEY-----\n!!!\n-----END PUBLIC KEY-----',
    '-----BEGIN PUBLIC KEY-----\n-----END PUBLIC KEY-----', '{"code":"no_anchor_key"}']) {
    assert.equal(await pemFingerprint(text, 'anchor'), null, text)
  }
})
