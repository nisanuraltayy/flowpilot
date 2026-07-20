"""Bounded context: authorization — merkezi yetki sınırı (`authorize`).

İlk iş kodu FP-E03-001 (Dilim A) ile geldi: davet yönetimi permission'ları ve
membership rolüne göre karar veren minimal, genişletilebilir bir policy. Dağınık
route-level `if role == "..."` kontrolü YASAKtır — kararlar buradan geçer.
Public sözleşme `authorization.application.access` altındadır. Bkz. README.md.
"""
