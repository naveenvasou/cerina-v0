"""
Pydantic schemas for Critic Agent outputs.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class CritiqueItem(BaseModel):
    """A single critique issue identified by a critic."""
    issue: str = Field(..., description="Description of the issue found")
    severity: Literal["critical", "major", "minor"] = Field(..., description="Severity level")
    location: Optional[str] = Field(None, description="Section or location reference in the draft")
    recommendation: str = Field(..., description="Specific actionable recommendation to fix the issue")


class SafetyCritique(BaseModel):
    """Output from the Safety Critic agent."""
    approved: bool = Field(..., description="Whether the draft passes safety review")
    issues: List[CritiqueItem] = Field(default_factory=list, description="List of safety issues found")
    summary: str = Field(..., description="Brief summary of safety evaluation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "approved": False,
                "issues": [
                    {
                        "issue": "Contains flooding technique without consent check",
                        "severity": "critical",
                        "location": "Step 5",
                        "recommendation": "Add grounding techniques and explicit consent checkpoint before exposure"
                    }
                ],
                "summary": "Draft requires safety modifications before proceeding"
            }
        }


class ClinicalAccuracyCritique(BaseModel):
    """Output from the Clinical Accuracy Critic agent."""
    approved: bool = Field(..., description="Whether the draft passes clinical accuracy review")
    issues: List[CritiqueItem] = Field(default_factory=list, description="List of clinical accuracy issues")
    evidence_gaps: List[str] = Field(default_factory=list, description="Areas lacking evidence-based support")
    summary: str = Field(..., description="Brief summary of clinical accuracy evaluation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "approved": True,
                "issues": [],
                "evidence_gaps": ["SUDS progression could use more gradual steps"],
                "summary": "Draft is clinically sound with minor enhancement opportunities"
            }
        }


class ToneEmpathyCritique(BaseModel):
    """Output from the Tone/Empathy Critic agent."""
    approved: bool = Field(..., description="Whether the draft passes tone/empathy review")
    issues: List[CritiqueItem] = Field(default_factory=list, description="List of tone/empathy issues")
    tone_score: int = Field(..., ge=1, le=10, description="Overall tone score from 1-10")
    summary: str = Field(..., description="Brief summary of tone/empathy evaluation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "approved": True,
                "issues": [],
                "tone_score": 8,
                "summary": "Warm and supportive tone throughout with good therapeutic alliance language"
            }
        }


class ConsolidatedCritique(BaseModel):
    """
    Final consolidated critique from all 3 critic agents.
    Used as the critique_document in state.
    """
    overall_approved: bool = Field(..., description="True only if ALL 3 critics approve")
    iteration: int = Field(..., description="Current reflection iteration number")
    
    # Individual critic outputs
    safety: SafetyCritique = Field(..., description="Safety critic evaluation")
    clinical_accuracy: ClinicalAccuracyCritique = Field(..., description="Clinical accuracy evaluation")
    tone_empathy: ToneEmpathyCritique = Field(..., description="Tone/empathy evaluation")
    
    # Synthesized outputs
    final_summary: str = Field(..., description="Consolidated summary of all critiques")
    action_items: List[str] = Field(default_factory=list, description="Prioritized list of revisions needed")
    
    def to_markdown(self) -> str:
        """Convert critique to readable Markdown for display."""
        lines = ["# Critique Report\n"]
        lines.append(f"**Iteration:** {self.iteration}")
        lines.append(f"**Overall Status:** {'✅ Approved' if self.overall_approved else '❌ Requires Revision'}\n")
        
        # Safety Section
        lines.append("## 🛡️ Safety Review")
        lines.append(f"**Status:** {'✅ Passed' if self.safety.approved else '❌ Failed'}")
        lines.append(f"**Summary:** {self.safety.summary}")
        if self.safety.issues:
            lines.append("\n**Issues:**")
            for issue in self.safety.issues:
                severity_icon = "🔴" if issue.severity == "critical" else "🟠" if issue.severity == "major" else "🟡"
                lines.append(f"- {severity_icon} **{issue.severity.upper()}**: {issue.issue}")
                if issue.location:
                    lines.append(f"  - *Location:* {issue.location}")
                lines.append(f"  - *Fix:* {issue.recommendation}")
        lines.append("")
        
        # Clinical Accuracy Section
        lines.append("## 🩺 Clinical Accuracy Review")
        lines.append(f"**Status:** {'✅ Passed' if self.clinical_accuracy.approved else '❌ Failed'}")
        lines.append(f"**Summary:** {self.clinical_accuracy.summary}")
        if self.clinical_accuracy.issues:
            lines.append("\n**Issues:**")
            for issue in self.clinical_accuracy.issues:
                severity_icon = "🔴" if issue.severity == "critical" else "🟠" if issue.severity == "major" else "🟡"
                lines.append(f"- {severity_icon} **{issue.severity.upper()}**: {issue.issue}")
                if issue.location:
                    lines.append(f"  - *Location:* {issue.location}")
                lines.append(f"  - *Fix:* {issue.recommendation}")
        if self.clinical_accuracy.evidence_gaps:
            lines.append("\n**Evidence Gaps:**")
            for gap in self.clinical_accuracy.evidence_gaps:
                lines.append(f"- {gap}")
        lines.append("")
        
        # Tone/Empathy Section
        lines.append("## 💚 Tone & Empathy Review")
        lines.append(f"**Status:** {'✅ Passed' if self.tone_empathy.approved else '❌ Failed'}")
        lines.append(f"**Tone Score:** {self.tone_empathy.tone_score}/10")
        lines.append(f"**Summary:** {self.tone_empathy.summary}")
        if self.tone_empathy.issues:
            lines.append("\n**Issues:**")
            for issue in self.tone_empathy.issues:
                severity_icon = "🔴" if issue.severity == "critical" else "🟠" if issue.severity == "major" else "🟡"
                lines.append(f"- {severity_icon} **{issue.severity.upper()}**: {issue.issue}")
                if issue.location:
                    lines.append(f"  - *Location:* {issue.location}")
                lines.append(f"  - *Fix:* {issue.recommendation}")
        lines.append("")
        
        # Action Items
        if self.action_items:
            lines.append("## 📋 Action Items for Revision")
            for i, item in enumerate(self.action_items, 1):
                lines.append(f"{i}. {item}")
        
        return "\n".join(lines)
