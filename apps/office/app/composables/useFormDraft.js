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

// Định dạng ngày giờ theo kiểu Việt Nam (dd/mm/yyyy), dùng chung cho mọi trang.

const PREFIX = 'moc-draft:';
export function dropDrafts() {
    try {
        for (const k of Object.keys(sessionStorage))if (k.startsWith(PREFIX)) sessionStorage.removeItem(k);
    } catch  {}
}
export function useFormDraft(key, read, write) {
    let enabled = false;
    const storageKey = ()=>{
        const k = key();
        return k ? `${PREFIX}${k}` : null;
    };
    watch(read, (value)=>{
        const k = storageKey();
        if (!enabled || !k) return;
        try {
            if (value === null) sessionStorage.removeItem(k);
            else sessionStorage.setItem(k, JSON.stringify(value));
        } catch  {}
    }, {
        deep: true
    });
    function resume() {
        enabled = true;
        const k = storageKey();
        if (!k) return false;
        try {
            const raw = sessionStorage.getItem(k);
            if (!raw) return false;
            write(JSON.parse(raw));
            return true;
        } catch  {
            return false;
        }
    }
    function clear() {
        enabled = false;
        const k = storageKey();
        if (!k) return;
        try {
            sessionStorage.removeItem(k);
        } catch  {}
    }
    onBeforeRouteLeave(()=>clear());
    return {
        resume,
        clear
    };
}
