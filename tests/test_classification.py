import unittest
from pathlib import Path

from agent_workflow import orchestrate_change_analysis
from guided_decision import filter_rows_by_condition_answers, parse_conditions, unique_conditions_for_rows
from llm_utils import NO_MATCH_MESSAGE, keyword_classify_change, load_reference_table
from main import get_required_documents, suggest_process
from upload_review import extract_uploaded_text, review_uploaded_document


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_PATH = PROJECT_ROOT / "EU_TypeIB_Created.xlsx"
COUNTRY_WORKBOOKS = {
    "Australia": PROJECT_ROOT / "Australia.xlsx",
    "Canada": PROJECT_ROOT / "Canada.xlsx",
    "EU": PROJECT_ROOT / "EU_TypeIB_Created.xlsx",
    "Switzerland": PROJECT_ROOT / "Switzerland_TypeIB_Created.xlsx",
}


class ClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference_df = load_reference_table(str(WORKBOOK_PATH))

    def test_invented_name_query_maps_to_centralized_entry(self):
        result = keyword_classify_change(
            "Change the invented name of the finished product for a centrally authorised medicinal product.",
            self.reference_df,
        )
        self.assertEqual(result["procedure_type"], "Type IA - IN")
        self.assertIn("centrally authorised", result["description"].lower())

    def test_all_country_workbooks_load_with_normalized_columns(self):
        for expected_market, workbook_path in COUNTRY_WORKBOOKS.items():
            with self.subTest(market=expected_market):
                country_df = load_reference_table(str(workbook_path))
                self.assertFalse(country_df.empty)
                self.assertIn("change_item", country_df.columns)
                self.assertIn("conditions", country_df.columns)
                markets = {
                    str(value).strip()
                    for value in country_df["market"].dropna().unique()
                }
                self.assertIn(expected_market, markets)

    def test_every_country_reference_produces_complete_end_user_output(self):
        required_fields = {
            "market",
            "change_type",
            "description",
            "category",
            "procedure_type",
            "filing_required",
            "filing_description",
            "required_documents_list",
            "recommended_process",
            "action_plan",
        }
        for expected_market, workbook_path in COUNTRY_WORKBOOKS.items():
            country_df = load_reference_table(str(workbook_path))
            for _, row in country_df.iterrows():
                with self.subTest(market=expected_market, reference_id=row["reference_id"]):
                    result = orchestrate_change_analysis(
                        str(row["change_item"]),
                        country_df,
                        vectorstore=None,
                        selected_reference_id=str(row["reference_id"]),
                        user_decisions={"reference_id": str(row["reference_id"])},
                    )
                    self.assertNotIn("error", result)
                    self.assertTrue(required_fields.issubset(result))
                    self.assertEqual(result["market"], expected_market)
                    self.assertTrue(str(result["procedure_type"]).strip())
                    self.assertTrue(str(result["filing_description"]).strip())
                    self.assertTrue(result["action_plan"])

    def test_unmatched_description_uses_health_authority_message(self):
        result = keyword_classify_change(
            "zzzxxyy unmatched regulatory scenario 987654321",
            self.reference_df,
        )
        self.assertEqual(result, {"error": NO_MATCH_MESSAGE})

    def test_invalid_guided_reference_uses_health_authority_message(self):
        result = orchestrate_change_analysis(
            "A proposed change",
            self.reference_df,
            vectorstore=None,
            selected_reference_id="does-not-exist",
        )
        self.assertEqual(result["error"], NO_MATCH_MESSAGE)

    def test_atc_code_query_returns_expected_documents(self):
        result = keyword_classify_change(
            "We need to update the ATC code after a WHO change.",
            self.reference_df,
        )
        docs = get_required_documents(result)
        self.assertEqual(result["procedure_type"], "Type IA")
        self.assertTrue(any("ATC Code list" in doc for doc in docs))

    def test_packaging_component_query_returns_type_ia(self):
        result = keyword_classify_change(
            "Change in name of the packaging component while the component remains unchanged.",
            self.reference_df,
        )
        self.assertEqual(result["procedure_type"], "Type IA - IN")
        self.assertIn("packaging component", result["description"].lower())

    def test_process_guidance_for_type_ib(self):
        result = keyword_classify_change(
            "Change the invented name of the finished product for a nationally authorised medicinal product.",
            self.reference_df,
        )
        process = suggest_process(result)
        self.assertEqual(result["procedure_type"], "Type IB")
        self.assertIn("before implementation", process.lower())

    def test_orchestrator_adds_agentic_workflow_fields(self):
        result = orchestrate_change_analysis(
            "We need to update the ATC code after a WHO change.",
            self.reference_df,
            vectorstore=None,
        )
        self.assertEqual(result["procedure_type"], "Type IA")
        self.assertIn("workflow_steps", result)
        self.assertIn("action_plan", result)
        self.assertEqual(result["match_method"], "keyword")
        self.assertTrue(result["tool_trace"])
        self.assertEqual(result["risk_level"], "low")

    def test_orchestrator_uses_guided_reference_selection(self):
        initial = keyword_classify_change(
            "Change the invented name of the finished product for a nationally authorised medicinal product.",
            self.reference_df,
        )
        result = orchestrate_change_analysis(
            "Change the invented name of the finished product.",
            self.reference_df,
            vectorstore=None,
            selected_reference_id=initial["reference_id"],
            user_decisions={"change_type": initial["change_type"], "reference_id": initial["reference_id"]},
        )
        self.assertEqual(result["reference_id"], initial["reference_id"])
        self.assertEqual(result["procedure_type"], "Type IB")
        self.assertEqual(result["match_method"], "guided_decision_tree")
        self.assertEqual(result["confidence"], "high")
        self.assertFalse(result["needs_clarification"])

    def test_condition_parser_extracts_numbered_conditions(self):
        conditions = parse_conditions(
            "All Conditions are met:\n"
            "1. The packaging component must remain unchanged.\n"
            "2. The deletion should not be due to critical deficiencies concerning manufacturing."
        )
        self.assertEqual(len(conditions), 2)
        self.assertIn("packaging component", conditions[0])

    def test_condition_parser_handles_no_conditions(self):
        self.assertEqual(parse_conditions("No Conditions"), [])
        self.assertEqual(parse_conditions(""), [])

    def test_condition_parser_hides_not_met_heading(self):
        conditions = parse_conditions(
            "If any condition is not met:\n"
            "1. The API must not be sterile.\n"
            "2. The container must be more protective."
        )
        self.assertEqual(len(conditions), 2)
        self.assertNotIn("If any condition is not met", conditions[0])

    def test_condition_answers_route_to_met_scenario(self):
        subset = self.reference_df[
            self.reference_df["change_type"].astype(str)
            == "Change in Site for Manufacturing, Packaging, Batch release"
        ]
        conditions = unique_conditions_for_rows(subset)
        narrowed = filter_rows_by_condition_answers(subset, {condition: "Yes" for condition in conditions[:2]})
        self.assertFalse(narrowed.empty)
        combined_conditions = " ".join(narrowed["conditions"].fillna("").astype(str)).lower()
        self.assertIn("all condition", combined_conditions)
        self.assertNotIn("if any condition is not met", combined_conditions)

    def test_condition_answers_route_to_not_met_scenario(self):
        subset = self.reference_df[
            self.reference_df["change_type"].astype(str)
            == "Change in Site for Manufacturing, Packaging, Batch release"
        ]
        conditions = unique_conditions_for_rows(subset)
        narrowed = filter_rows_by_condition_answers(subset, {conditions[0]: "No"})
        self.assertFalse(narrowed.empty)
        combined = " ".join(narrowed["conditions"].fillna("").astype(str)).lower()
        self.assertTrue("not met" in combined or "no conditions" in combined)

    def test_condition_answers_with_not_sure_do_not_force_filtering(self):
        subset = self.reference_df[
            self.reference_df["change_type"].astype(str)
            == "Change in Site for Manufacturing, Packaging, Batch release"
        ]
        narrowed = filter_rows_by_condition_answers(subset, {"uncertain condition": "Not sure"})
        self.assertEqual(len(narrowed), len(subset))

    def test_guided_selection_can_analyze_every_reference_row(self):
        for _, row in self.reference_df.iterrows():
            result = orchestrate_change_analysis(
                str(row["change_item"]),
                self.reference_df,
                vectorstore=None,
                selected_reference_id=str(row["reference_id"]),
                user_decisions={"reference_id": str(row["reference_id"])},
            )
            self.assertNotIn("error", result)
            self.assertEqual(str(result["reference_id"]), str(row["reference_id"]))
            self.assertEqual(result["confidence"], "high")

    def test_orchestrator_flags_ambiguous_request(self):
        result = orchestrate_change_analysis(
            "Change the invented name of the finished product.",
            self.reference_df,
            vectorstore=None,
        )
        self.assertTrue(result["needs_clarification"])
        self.assertTrue(result["clarification_questions"])

    def test_orchestrator_flags_ambiguous_manufacturing_request(self):
        result = orchestrate_change_analysis(
            "We are updating manufacturing details for the product.",
            self.reference_df,
            vectorstore=None,
        )
        self.assertTrue(result["needs_clarification"])

    def test_clarification_hint_prefers_type_ib(self):
        result = orchestrate_change_analysis(
            "Change the invented name of the finished product. Additional context: Which filing pathway fits better: Type IB",
            self.reference_df,
            vectorstore=None,
        )
        self.assertEqual(result["procedure_type"], "Type IB")

    def test_csv_upload_extraction_and_review(self):
        csv_bytes = b"document_name,details\nATC Evidence,Proof of acceptance by WHO and copy of the ATC Code list\n"
        extracted = extract_uploaded_text("supporting_docs.csv", csv_bytes)
        self.assertIn("ATC Evidence", extracted)

        classification = keyword_classify_change(
            "We need to update the ATC code after a WHO change.",
            self.reference_df,
        )
        classification["required_documents_list"] = get_required_documents(classification)
        review = review_uploaded_document("supporting_docs.csv", extracted, classification)
        self.assertTrue(review["matched_requirements"])

    def test_orchestrator_includes_uploaded_document_review(self):
        result = orchestrate_change_analysis(
            "We need to update the ATC code after a WHO change.",
            self.reference_df,
            vectorstore=None,
            uploaded_document={
                "name": "supporting_notes.txt",
                "text": "Proof of acceptance by WHO and copy of the ATC Code list attached.",
            },
        )
        self.assertIn("uploaded_document_review", result)
        self.assertEqual(result["uploaded_document_review"]["upload_name"], "supporting_notes.txt")


if __name__ == "__main__":
    unittest.main()
