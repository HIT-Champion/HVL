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

// Trang tài liệu của Signet (#308). Đọc thẳng tệp .md trong kho, không chép: gốc nội dung là gốc repo, include chỉ lấy
// docs/ và các README đã liệt kê. Tệp .md đọc như CommonMark (markdown.format 'detect'), nên dấu <, { trong tài liệu
// không làm hỏng bước dựng như MDX. Liên kết tới tệp mã, thư mục chuyển thành liên kết GitHub
// (src/remark/lien-ket-kho.js).

import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {GlobExcludeDefault} from '@docusaurus/utils';
import {themes as prismThemes} from 'prism-react-renderer';
import lienKetKho, {taoBoLoc} from './src/remark/lien-ket-kho.js';

const KHO = 'https://github.com/HIT-Champion/Signet';
const NHANH = 'develop';
const GOC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

// Tệp đưa lên trang, tính từ gốc repo. Chỉ lấy README đúng một cấp để không quét vào node_modules của ứng dụng
const INCLUDE = [
  'docs/**/*.md',
  'README.md',
  'README.en.md',
  'CHANGELOG.md',
  'ROADMAP.md',
  'CONTRIBUTING.md',
  'SECURITY.md',
  'DEPENDENCIES.md',
  'CODE_OF_CONDUCT.md',
  'services/*/README.md',
  'apps/*/README.md',
  'platform/README.md',
  'platform/*/README.md',
  'db/README.md',
  'schemas/README.md',
];
// Giữ mẫu bỏ qua mặc định của Docusaurus; nghiên cứu trước đề là tài liệu nội bộ, không đưa lên
const EXCLUDE = [...GlobExcludeDefault, '**/node_modules/**', 'website/**', 'docs/du-thi/nghien-cuu/**'];

// Giấy phép SIL OFL-1.1 đi cùng tệp phông Be Vietnam Pro đóng vào bản dựng, như image app-office (#305)
function giayPhepPhong(context) {
  return {
    name: 'giay-phep-phong',
    async postBuild({outDir}) {
      const dich = path.join(outDir, 'fonts', 'be-vietnam-pro');
      await fs.mkdir(dich, {recursive: true});
      const goi = path.join(context.siteDir, 'node_modules', '@fontsource', 'be-vietnam-pro');
      await fs.copyFile(path.join(goi, 'LICENSE'), path.join(dich, 'OFL.txt'));
    },
  };
}

/** @type {import('@docusaurus/types').Config} */
export default {
  title: 'Signet',
  tagline: 'Lõi nền tảng nguồn mở, tự cài, đóng dấu tin cậy lên mọi thứ đi qua nó',
  favicon: 'img/favicon.svg',
  url: 'https://hit-champion.github.io',
  baseUrl: '/Signet/',
  organizationName: 'HIT-Champion',
  projectName: 'Signet',
  trailingSlash: false,

  onBrokenLinks: 'throw',
  onBrokenAnchors: 'warn',
  markdown: {
    format: 'detect',
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'throw',
      onBrokenMarkdownImages: 'throw',
    },
  },

  i18n: {
    defaultLocale: 'vi',
    locales: ['vi'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          path: '..',
          include: INCLUDE,
          exclude: EXCLUDE,
          routeBasePath: 'tai-lieu',
          sidebarPath: './sidebars.js',
          editUrl: ({docPath}) => `${KHO}/edit/${NHANH}/${docPath}`,
          beforeDefaultRemarkPlugins: [
            [lienKetKho, {goc: GOC, dangLen: taoBoLoc(GOC, INCLUDE, EXCLUDE), kho: KHO, nhanh: NHANH}],
          ],
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themes: [
    '@docusaurus/theme-mermaid',
    [
      '@easyops-cn/docusaurus-search-local',
      // Chỉ mục tìm kiếm dựng sẵn lúc build, tìm ngay trong trình duyệt, không gọi dịch vụ ngoài. docsDir chỉ dùng để
      // tính mã băm trong tên tệp chỉ mục (đổi tài liệu thì trình duyệt tải chỉ mục mới)
      {
        hashed: true,
        docsDir: ['../docs'],
        language: ['vi', 'en'],
        indexBlog: false,
        indexPages: false,
        docsRouteBasePath: 'tai-lieu',
        highlightSearchTermsOnTargetPage: true,
        explicitSearchResultPath: true,
      },
    ],
  ],

  // Phông Be Vietnam Pro tự phục vụ từ gói npm, cùng phông của giao diện ứng dụng
  clientModules: ['./src/phong-chu.js'],
  plugins: [giayPhepPhong],

  /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
  themeConfig: {
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Signet',
      logo: {
        alt: 'Biểu tượng Signet',
        src: 'img/signet.svg',
        srcDark: 'img/signet-white.svg',
      },
      items: [
        {type: 'docSidebar', sidebarId: 'taiLieu', position: 'left', label: 'Tài liệu'},
        {type: 'doc', docId: 'docs/du-thi/README', position: 'left', label: 'Dự thi'},
        {type: 'doc', docId: 'CHANGELOG', position: 'left', label: 'Thay đổi'},
        {href: 'https://signet.htechcs.com', label: 'Bản online', position: 'right'},
        {href: KHO, label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Tài liệu',
          items: [
            {label: 'Xem nhanh 5 phút', to: '/tai-lieu/docs'},
            {label: 'Cài đặt từ mã nguồn', to: '/tai-lieu#cài-đặt-từ-mã-nguồn-building-from-source'},
            {label: 'Triển khai, nâng cấp', to: '/tai-lieu/docs/trien-khai'},
            {label: 'English overview', to: '/tai-lieu/README.en'},
          ],
        },
        {
          title: 'Mã nguồn',
          items: [
            {label: 'GitHub', href: KHO},
            {label: 'Bản phát hành', href: `${KHO}/releases`},
            {label: 'Báo lỗi, góp ý', href: `${KHO}/issues`},
          ],
        },
        {
          title: 'Giấy phép',
          items: [
            {label: 'Apache-2.0', href: `${KHO}/blob/${NHANH}/LICENSE`},
            {label: 'Phụ thuộc và giấy phép', to: '/tai-lieu/DEPENDENCIES'},
          ],
        },
      ],
      copyright: '© 2026 Signet Team. Mã nguồn và tài liệu theo giấy phép Apache-2.0.',
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'sql', 'nginx'],
    },
    mermaid: {
      theme: {light: 'neutral', dark: 'dark'},
    },
  },
};
