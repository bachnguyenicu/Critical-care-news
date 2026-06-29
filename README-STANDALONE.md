# Critical Care Daily - standalone academic setup

Ban nay tach khoi Claude. Ung dung van la GitHub Pages tinh (`index.html` doc `digest.json`), nhung lich cap nhat hang ngay chay bang GitHub Actions trong repo, khong can mo Claude hay may ca nhan.

Phien ban nay nang cap noi dung theo huong journal club:

- Quick Listen: transcript ngan de nghe moi sang.
- Academic Summary: tom tat abstract co uu tien cau co so lieu.
- PICO: population, intervention/exposure, comparator, outcomes.
- Key Results: cac cau ket qua chinh, uu tien effect size/CI/so lieu neu abstract co.
- Critical Appraisal: diem can kiem tra ve bias, heterogeneity, applicability.
- Bedside Impact: co nen thay doi thuc hanh hay chi nen doc them.
- Medical English: cum academic va tu vung de luyen noi/doc journal.

## Cach cai vao repo hien tai

1. Mo repo `bachnguyenicu/Critical-care-news`.
2. Copy cac file/folder nay vao root cua repo, ghi de file cu neu GitHub hoi:
   - `index.html`
   - `digest.json`
   - `scripts/update_digest.py`
   - `.github/workflows/daily-digest.yml`
3. Commit va push len branch `main`.
4. Vao GitHub repo -> Settings -> Actions -> General.
5. O muc Workflow permissions, chon `Read and write permissions`, roi Save.
6. Vao tab Actions -> `Daily critical care digest` -> `Run workflow` de test ngay.

Sau do GitHub se tu chay moi ngay luc 05:30 gio Viet Nam/Asia-Barnaul va commit `digest.json`. GitHub Pages se tu phuc vu ban moi nhat tai:

https://bachnguyenicu.github.io/Critical-care-news/

## Khong con phu thuoc Claude

- Khong dung Claude scheduled task.
- Khong can Claude desktop dang mo.
- Khong can GitHub PAT rieng, vi workflow dung `GITHUB_TOKEN` noi bo cua GitHub.
- Khong co secret bi nhung trong file.

## Gioi han quan trong

Script nay dung PubMed metadata va abstracts, khong dung LLM. Vi vay no doc lap, mien phi, va ben hon, nhung khong doc full text va khong the thay the critical appraisal that su. Hay mo link PubMed/full text truoc khi ap dung vao thuc hanh.

Neu sau nay ban muon phan tich sau hon nua, co the them LLM provider vao workflow de doc abstract va tao appraisal giong nguoi hon. Khi do can API key rieng va co the co chi phi.

## Tuy chinh

- Sua gio chay trong `.github/workflows/daily-digest.yml`.
- Sua email `NCBI_EMAIL` thanh email cua ban de lich su dung PubMed E-utilities tot hon.
- Sua query trong `scripts/update_digest.py`, bien `SEARCH_TERMS`, neu muon uu tien chu de nhu sepsis, ARDS, ECMO, VAP, sedation, renal replacement therapy.
- Sua bo loc `ICU_RELEVANCE_PATTERN` neu muon rong/hẹp hon.
