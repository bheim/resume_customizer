# New Conversational Prompts - Usage Guide

## Overview

I've implemented your 4 improved LLM prompts! These provide a more natural, conversational approach to gathering context and generating bullets.

---

## 🎯 New Functions in `llm_utils.py`

### 1. **`generate_conversational_question(bullet_text)`**
Opens a friendly conversation instead of formal Q&A.

**Your Prompt:**
- "You are a professional resume coach conducting a friendly interview..."
- Ask 1-2 questions at a time
- Dig deeper for specifics when answers are vague
- Natural conversation, not interrogation

**Usage:**
```python
from llm_utils import generate_conversational_question

question = generate_conversational_question(
    "Led development of customer analytics dashboard"
)

print(question)
# Output: "Let's talk about this experience! Tell me the story -
#          what did this role actually involve? What were you doing
#          day-to-day, and what results did you achieve?"
```

---

### 2. **`extract_facts_from_conversation(bullet_text, conversation_history)`**
Extracts structured facts from natural conversation.

**Your Prompt:**
- Extract: situation, actions, results, skills, tools, timeline
- Be specific and preserve numbers
- Output structured JSON

**Usage:**
```python
from llm_utils import extract_facts_from_conversation

conversation = """
Q: Tell me about this dashboard project.
A: I led a team of 3 engineers to build a customer analytics dashboard.
   We used React and Python FastAPI. The project took 6 months and now
   50+ stakeholders use it daily. It reduced report generation time from
   2 hours to 15 minutes.
"""

facts = extract_facts_from_conversation(
    "Led development of customer analytics dashboard",
    conversation
)

print(facts)
# Output:
# {
#   "situation": "Led team of 3 engineers on 6-month project",
#   "actions": [
#     "Led development team",
#     "Built customer analytics dashboard"
#   ],
#   "results": [
#     "Reduced report time from 2 hours to 15 minutes",
#     "Used by 50+ stakeholders daily"
#   ],
#   "skills": ["Leadership", "Full-stack development"],
#   "tools": ["React", "Python", "FastAPI"],
#   "timeline": "6 months"
# }
```

---

### 3. **`extract_jd_keywords(job_description)`**
Extracts key requirements from job description.

**Your Prompt:**
- Extract: required skills, nice-to-have skills, responsibilities, experience level
- Focus on technical requirements and industry terms

**Usage:**
```python
from llm_utils import extract_jd_keywords

jd = """
Senior Data Engineer

Requirements:
- 5+ years Python experience
- Experience with React and FastAPI
- Strong SQL and data modeling skills
- AWS or GCP cloud experience
- Nice to have: Kubernetes, Docker

Responsibilities:
- Build data pipelines and analytics platforms
- Mentor junior engineers
"""

keywords = extract_jd_keywords(jd)

print(keywords)
# Output:
# {
#   "required_skills": ["Python", "React", "FastAPI", "SQL", "AWS/GCP"],
#   "nice_to_have_skills": ["Kubernetes", "Docker"],
#   "key_responsibilities": [
#     "Build data pipelines and analytics platforms",
#     "Mentor junior engineers"
#   ],
#   "experience_level": "5+ years senior level",
#   "industry_context": "Data engineering and analytics"
# }
```

**Cached:** Results are cached by JD hash for performance!

---

### 4. **`generate_bullet_with_keywords(original, facts, jd_keywords, char_limit)`**
Generates enhanced bullet using XYZ format.

**Your Prompt:**
- XYZ format: "Accomplished [X] as measured by [Y] by doing [Z]"
- Strong action verbs
- Include metrics from facts
- Naturally integrate JD keywords
- Under character limit (default 150)
- NEVER invent details

**Usage:**
```python
from llm_utils import generate_bullet_with_keywords, extract_facts_from_conversation, extract_jd_keywords

# Get facts and keywords first
facts = extract_facts_from_conversation(bullet, conversation)
keywords = extract_jd_keywords(job_description)

# Generate enhanced bullet
enhanced = generate_bullet_with_keywords(
    original_bullet="Led development of dashboard",
    extracted_facts=facts,
    jd_keywords=keywords,
    char_limit=150
)

print(enhanced)
# Output: "Led development of customer analytics dashboard using React and
#          Python FastAPI, reducing report generation time from 2 hours to
#          15 minutes for 50+ stakeholders"
```

---

## 🔄 Complete Workflow Example

```python
from llm_utils import (
    generate_conversational_question,
    extract_facts_from_conversation,
    extract_jd_keywords,
    generate_bullet_with_keywords
)

# 1. Start conversation
bullet = "Led development of analytics dashboard"
opening_question = generate_conversational_question(bullet)

# User answers in natural conversation...
conversation = """
Q: {opening_question}
A: I worked on this for about 6 months with a team of 3. We built it with
   React on the frontend and Python FastAPI for the backend. The main win
   was cutting report time from 2 hours to 15 minutes. Now 50+ people across
   marketing and sales use it daily.

Q: What were the main technical challenges?
A: The biggest challenge was integrating with our legacy data warehouse.
   We had to build custom ETL pipelines. Also needed to ensure the dashboard
   could handle real-time updates without performance issues.
"""

# 2. Extract structured facts
facts = extract_facts_from_conversation(bullet, conversation)

# 3. Extract JD keywords
jd = "Senior Data Engineer... Python, React, data pipelines..."
keywords = extract_jd_keywords(jd)

# 4. Generate enhanced bullet
enhanced_bullet = generate_bullet_with_keywords(
    original_bullet=bullet,
    extracted_facts=facts,
    jd_keywords=keywords,
    char_limit=150
)

print(enhanced_bullet)
# Output: "Led development of real-time analytics dashboard using React and
#          Python FastAPI, reducing report generation from 2 hours to 15
#          minutes for 50+ stakeholders across marketing and sales teams"
```

---

## 🎨 Key Differences from Old Approach

| Feature | Old Approach | New Approach |
|---------|-------------|--------------|
| **Tone** | Formal Q&A | Conversational interview |
| **Structure** | Rigid categories | Natural conversation flow |
| **Fact Format** | Nested JSONB | Flat, clear structure |
| **JD Analysis** | Simple term extraction | Structured requirements |
| **Bullet Format** | Variable | Strict XYZ format |
| **Character Limit** | Post-generation enforcement | Built into prompt |

---

## 📊 Fact Structure Comparison

### Old (extract_facts_from_qa):
```json
{
  "metrics": {
    "quantifiable_achievements": [...],
    "scale": [...]
  },
  "technical_details": {
    "technologies": [...],
    "methodologies": [...]
  },
  ...
}
```

### New (extract_facts_from_conversation):
```json
{
  "situation": "string",
  "actions": ["action 1", "action 2"],
  "results": ["result 1", "result 2"],
  "skills": ["skill 1", "skill 2"],
  "tools": ["tool 1", "tool 2"],
  "timeline": "when"
}
```

**Simpler and more intuitive!**

---

## 🚀 Integration with Existing Code

Both old and new functions work! You can:

**Option 1: Use new functions for new features**
```python
# For conversational "Add Context" flow
facts = extract_facts_from_conversation(bullet, conversation)
enhanced = generate_bullet_with_keywords(bullet, facts, keywords)
```

**Option 2: Keep old functions for existing flows**
```python
# For existing Q&A flow
facts = extract_facts_from_qa(bullet, qa_pairs)
enhanced = generate_bullet_with_facts(bullet, jd, facts)
```

**Option 3: Gradual migration**
- New users: Conversational approach
- Existing users: Keep old approach
- A/B test to see which generates better bullets

---

## 🧪 Testing the New Prompts

```python
# Quick test script
from llm_utils import (
    generate_conversational_question,
    extract_facts_from_conversation,
    extract_jd_keywords,
    generate_bullet_with_keywords
)

# Test 1: Conversational question
bullet = "Built microservices platform"
q = generate_conversational_question(bullet)
print("Question:", q)

# Test 2: Fact extraction
conversation = """
Q: Tell me about the microservices platform.
A: Built it with Python and Docker. Scaled to handle 10M requests/day.
   Team of 5 engineers, took 8 months.
"""
facts = extract_facts_from_conversation(bullet, conversation)
print("Facts:", facts)

# Test 3: JD keywords
jd = "Looking for Senior Engineer with Python, Docker, microservices experience"
keywords = extract_jd_keywords(jd)
print("Keywords:", keywords)

# Test 4: Bullet generation
enhanced = generate_bullet_with_keywords(bullet, facts, keywords, char_limit=150)
print("Enhanced:", enhanced)
```

---

## ✅ What You Get

✅ **Natural conversation flow** - Feels like talking to a coach, not filling a form
✅ **Structured fact extraction** - Clean, simple format
✅ **JD keyword integration** - Automatically emphasizes relevant skills
✅ **XYZ format enforcement** - Consistent, compelling bullets
✅ **Character limits** - Built into generation, not post-processing
✅ **Cached results** - JD analysis cached for performance

All your prompts are implemented and ready to use! 🎉
