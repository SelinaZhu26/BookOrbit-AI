# Use case → code → screen → tests

All 18 use cases of the Phase II design report, where each one lives, and the tests that check
its basic **and** alternative flows. `pytest` runs every test below; `tests/e2e_browser.py`
repeats the main flows in a real browser.

| UC | Name | Service method(s) | Screen (route) | Tests |
|----|------|-------------------|----------------|-------|
| UC-01 | Register an Account | `AuthService.register`, `validate_registration`, `face_embeddings` | Registration (`/register`) | `test_uc01_02_auth.py::test_register_*`, `test_ui_flows.py::test_register_*` |
| UC-02 | Log In Using Biometric Authentication | `AuthService.start_sign_in`, `verify_sign_in`, `lock_remaining_s` | Sign in (`/signin`) | `test_uc01_02_auth.py::test_login_*`, `test_three_failures_lock…`, `test_ui_flows.py::test_sign_in_wrong_face_then_lock` |
| UC-03 | View Popular Books | `RecommendationEngine.popular` | Home (`/`) for VS and SU | `test_uc03_06_catalog.py::test_popular_*`, `test_visitor_and_su_home…` |
| UC-04 | Browse and Search Books | `CatalogService.search`, `cover_search`; `CoverIndex.search` | Browse & Search (`/browse`, `/browse/cover`), Home search box | `test_uc03_06_catalog.py::test_browse_*`, `test_search_by_year…`, `test_cover_search_*`, `test_twelve_per_page…` |
| UC-05 | View Book Details and Reviews | `CatalogService.view`, `display_price`; `ReviewService.published` | Book Details & Reviews (`/books/<id>`) | `test_uc03_06_catalog.py::test_view_*`, `test_vip_sees_vip_price`, `test_removed_book…`, `test_ui_flows.py::test_book_details_buttons_by_role` |
| UC-06 | Receive Personalized Recommendations | `RecommendationEngine.personalized`, `profile` | Home "Recommended for you", Recommendations (`/recommendations`) | `test_uc03_06_catalog.py::test_personal_*`, `test_no_history…`, `test_fewer_scored…` |
| UC-07 | Manage Cash Balance and Ledger | `WalletService.deposit`, `ledger` | My Balance (`/balance`) | `test_uc07_09_money.py::test_deposit_*`, `test_invalid_deposits…`, `test_suspended_customer_can_deposit…`, `test_failed_save…` |
| UC-08 | Purchase Books | `PurchaseService.quote`, `checkout` | Checkout (`/checkout`), Receipt | `test_uc07_09_money.py::test_purchase_*`, `test_insufficient_funds…`, `test_fine_that_makes_balance_negative…`, `test_promotion_*`, `test_ui_flows.py::test_deposit_and_checkout…` |
| UC-09 | Receive VIP Discount | `PurchaseService.final_price` | Book price, Checkout summary | `test_uc07_09_money.py::test_vip_pays_90_percent…`, `test_demoted_customer_pays_full_price`, `test_promoted_customer_gets_discount_from_next_purchase` |
| UC-10 | Submit Book Reviews | `ReviewService.submit`, `ModerationEngine.check`, `RatingService.recalculate` | Book Details "Write a review" | `test_uc10_11_reviews.py::test_moderation_*`, `test_published_review…`, `test_verified_buyer_counts_double`, `test_more_than_3_ratings…`, `test_any_user_can_review…` |
| UC-11 | Receive Review Warnings | `WarningService.issue`, `StatusManager.demote_to_rc`, `suspend` | Book Details message, My Reviews (`/my-reviews`) | `test_uc10_11_reviews.py::test_blocked_comment…`, `test_rc_with_more_than_2_warnings…`, `test_vip_with_blocked_comment…` |
| UC-12 | Interact with AI Chatbot | `ChatbotService.ask`, `classify`, `store_answer`, `general_answer`, `account_answer`, `recommend_answer`, `book_text_answer`; `RAGRetriever.search`; `LLMClient.chat` | AI Chatbot (`/chat`) | `test_uc12_14_ai.py::test_store_question…`, `test_answers_get_richer…`, `test_general_question_*`, `test_infra.py::test_chatbot_end_to_end_with_real_client…` |
| UC-13 | Access Additional Chatbot Information | `ChatbotService.admin_answer`, `AdminService.finance_facts` | AI Chatbot as SU | `test_uc12_14_ai.py::test_admin_*` |
| UC-14 | Use Smart Reading Companion | `ReadingCompanion.open`, `act`, `check_answer` | Reading Companion (`/read/<id>`) | `test_uc12_14_ai.py::test_companion_*`, `test_non_owner_reads_chapter_1_only`, `test_offline_summary_quiz…`, `test_explain_*` |
| UC-15 | Add New Books | `CatalogService.add_book`, `index_book`, `index_pending` | Manage Books (`/admin/books`) | `test_uc15_18_admin.py::test_su_adds_book…`, `test_add_book_*`, `test_book_not_indexed_is_indexed_at_startup` |
| UC-16 | Manage Taboo Word List | `TabooService.add`, `edit`, `delete` | Taboo Words (`/admin/taboo`) | `test_uc15_18_admin.py::test_taboo_*`, `test_uc10_11_reviews.py::test_new_taboo_word_applies…` |
| UC-17 | Reopen Suspended Accounts | `AdminService.reopen`, `suspended`; `StatusManager.reopen` | User Management (`/admin/users`) | `test_uc15_18_admin.py::test_reopen_*` |
| UC-18 | View Book Classification Lists | `RatingService.order_lists`, `recalculate_all` | Reports (`/admin/reports`) | `test_uc15_18_admin.py::test_order_lists_sorted`, `test_recalculate_all…`, `test_empty_lists_message` |

Cross-cutting: every screen for every role renders (`test_ui_flows.py::test_every_screen_renders`),
role-based sidebars and permission redirects, wallet-only mode, the text-file store
(`test_infra.py`), the Ollama client against a stand-in Ollama server, and the real
YOLOv8-face + SFace pipeline (`test_real_face_models.py`, runs when you point it at two photos).
