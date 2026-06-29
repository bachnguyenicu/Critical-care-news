# Critical Care Daily - standalone setup

Ban nay tach khoi Claude. Ung dung van la GitHub Pages tinh (`index.html` doc `digest.json`), nhung lich cap nhat hang ngay chay bang GitHub Actions trong repo, khong can mo Claude hay may ca nhan.

## Cach cai vao repo hien tai

1. Mo repo `bachnguyenicu/Critical-care-news`.
2. Copy cac file/folder nay vao root cua repo:
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

Script nay dung PubMed metadata va abstracts, khong dung LLM. Vi vay no doc lap va ben hon, nhung phan phan tich se can than/trung lap hon so voi ban Claude viet tay. Neu sau nay ban muon summary sau hon, co the them mot provider LLM khac vao GitHub Actions, nhung do la tuy chon rieng.

## Tuy chinh

- Sua gio chay trong `.github/workflows/daily-digest.yml`.
- Sua email `NCBI_EMAIL` thanh email cua ban de lich su dung PubMed E-utilities tot hon.
- Sua query trong `scripts/update_digest.py`, bien `SEARCH_TERMS`, neu muon uu tien chu de nhu sepsis, ARDS, ECMO, VAP, sedation, renal replacement therapy.
