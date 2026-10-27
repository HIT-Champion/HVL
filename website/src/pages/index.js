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

// Trang chủ: giới thiệu một màn hình rồi dẫn vào tài liệu. Nội dung chi tiết nằm trong README và docs/, trang này
// không chép lại.

import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';
import anhDieuHanh from '../../../docs/anh/dieu-hanh.png';
import styles from './index.module.css';

// Bốn con dấu tin cậy, theo bảng ở mục Giới thiệu của README
const CON_DAU = [
  {
    ten: 'Biết ai đã làm',
    y: 'Mọi lời gọi mang danh tính SSO, kể cả của tác tử AI; vai trò quan trọng bắt buộc xác thực hai bước.',
  },
  {ten: 'Sạch', y: 'Tệp được quét mã độc trước khi lưu, tệp bẩn không chạm tới kho.'},
  {ten: 'Không sửa lén được', y: 'Mọi thay đổi vào sổ kiểm toán chuỗi băm; sửa lén thì make audit chỉ ra dòng bị sửa.'},
  {
    ten: 'Kiểm chứng được từ bên ngoài',
    y: 'Văn bản phát hành mang mã QR, SHA-256 và chữ ký số minh họa; cổng xác thực công khai, không cần đăng nhập.',
  },
];

const CAI_DAT = '/tai-lieu#cài-đặt-từ-mã-nguồn-building-from-source';

const LOI_VAO = [
  {ai: 'Ban giám khảo', viec: 'Lộ trình xem nhanh, bảng tự chấm PoF, hỏi đáp với hội đồng', to: '/tai-lieu/docs'},
  {ai: 'Người cài đặt', viec: 'Cài từ mã nguồn bằng bốn lệnh, chạy thử với tài khoản mẫu', to: CAI_DAT},
  {ai: 'Người vận hành', viec: 'Triển khai lên máy chủ, nâng cấp, sao lưu, giám sát', to: '/tai-lieu/docs/trien-khai'},
  {ai: 'Nhà phát triển', viec: 'Kiến trúc, mô hình dữ liệu, API, cắm thêm ứng dụng', to: '/tai-lieu/docs/architecture'},
];

const MO_TA =
  'Signet: lõi nền tảng nguồn mở, tự cài, đóng dấu tin cậy lên mọi thứ đi qua nó. Kèm Văn phòng điện tử theo ' +
  'Nghị định 30/2020/NĐ-CP.';

export default function TrangChu() {
  return (
    <Layout description={MO_TA}>
      <header className={styles.dau}>
        <div className="container">
          <img className={styles.bieuTuong} src={useBaseUrl('/img/signet.svg')} alt="" width="64" height="64" />
          <h1 className={styles.ten}>Signet</h1>
          <p className={styles.khau}>Lõi nền tảng nguồn mở, tự cài, đóng dấu tin cậy lên mọi thứ đi qua nó</p>
          <p className={styles.phu}>
            Kèm ứng dụng đầu tiên chạy trên lõi: Văn phòng điện tử quản lý văn bản đến, văn bản đi theo Nghị định
            30/2020/NĐ-CP. Sản phẩm dự thi OLP PMNM 2026, giấy phép Apache-2.0.
          </p>
          <div className={styles.nut}>
            <Link className="button button--primary button--lg" to="/tai-lieu/docs">
              Xem nhanh 5 phút
            </Link>
            <Link className="button button--secondary button--lg" to={CAI_DAT}>
              Cài đặt
            </Link>
            <Link className="button button--secondary button--lg" href="https://signet.htechcs.com">
              Dùng thử bản online
            </Link>
          </div>
        </div>
      </header>
      <main>
        <section className="container margin-vert--xl">
          <h2>Bốn con dấu tin cậy</h2>
          <p>Ứng dụng nào cắm vào lõi cũng có sẵn bốn thứ này, không phải tự làm.</p>
          <div className={styles.luoi}>
            {CON_DAU.map((d) => (
              <div key={d.ten} className={styles.the}>
                <h3>{d.ten}</h3>
                <p>{d.y}</p>
              </div>
            ))}
          </div>
        </section>
        <section className="container margin-vert--xl">
          <figure className={styles.anh}>
            <img
              src={anhDieuHanh}
              alt="Dashboard điều hành của Văn phòng điện tử"
              width="1366"
              height="1371"
              loading="lazy"
            />
            <figcaption>Dashboard điều hành của Văn phòng điện tử.</figcaption>
          </figure>
        </section>
        <section className="container margin-vert--xl">
          <h2>Đọc theo vai trò của bạn</h2>
          <div className={styles.luoi}>
            {LOI_VAO.map((l) => (
              <Link key={l.ai} className={styles.the} to={l.to}>
                <h3>{l.ai}</h3>
                <p>{l.viec}</p>
              </Link>
            ))}
          </div>
        </section>
      </main>
    </Layout>
  );
}
