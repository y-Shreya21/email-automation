"""
Professional Email Templates and Personalization Engine
"""
from typing import Dict, Any, Tuple, Optional
import jinja2
import pandas as pd

# Common words/patterns that harm deliverability
SPAM_TRIGGER_WORDS = [
    "100% free", "guaranteed", "urgent response", "act now", "risk-free", 
    "no risk", "cash", "prize", "winner", "exclusive deal", "wire transfer"
]

TEMPLATES = {
    "custom": {
        "name": "Targeted Candidate Outreach",
        "description": "Brief, high-impact outreach template with profile snapshot and achievements",
        "subject_formats": [
            "Application: {{target_role}} – {{my_name}}",
            "Exploring {{target_role}} Opportunities at {{company_display}} – {{my_name}}",
            "Inquiry: {{target_role}} at {{company_display}} ({{my_name}})"
        ],
        "text_body": """Hi {{salutation}},

Hope you’re doing well.

I know you probably receive a lot of emails every day, so I’ll keep this brief.

I’m currently a {{current_designation}} with {{experience_phrase}}, and I’m actively looking for opportunities as a {{target_role}}{% if company_display %} at {{company_display}}{% endif %}.

A quick snapshot of my profile:

• {{achievement_1}}
• {{achievement_2}}
• {{achievement_3}}

I’m reaching out in case there’s a suitable opening within your organization, either now or in the near future. If you feel my profile could be a good fit, I’d be grateful if you could consider my application.

{% if resume_attached %}I’ve attached my resume for your reference.{% endif %}
You can also explore my open-source projects on GitHub ({{github_url}}){% if portfolio_url %} and my live portfolio at {{portfolio_url}}{% endif %}.

Thank you for your time. I truly appreciate it, and I hope to hear from you if there’s an opportunity that matches my background.

Best Regards,
{{my_name}}
{% if contact_phone %}Phone: {{contact_phone}}
{% endif %}LinkedIn: {{linkedin_url}}
GitHub: {{github_url}}
{% if portfolio_url %}Portfolio: {{portfolio_url}}
{% endif %}
---
If you prefer not to receive future emails from me, simply reply with 'unsubscribe' and I will promptly update my records.
""",
        "html_body": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #222222; }
  p { margin: 0 0 14px 0; }
  ul { margin: 0 0 14px 0; padding-left: 20px; }
  li { margin-bottom: 6px; }
  a { color: #1a73e8; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .signature { margin-top: 20px; border-top: 1px solid #e0e0e0; padding-top: 12px; color: #444; }
  .footer { margin-top: 25px; font-size: 11px; color: #888888; }
</style>
</head>
<body>
<p>Hi {{salutation}},</p>

<p>Hope you’re doing well.</p>

<p>I know you probably receive a lot of emails every day, so I’ll keep this brief.</p>

<p>I’m currently a <strong>{{current_designation}}</strong> with {{experience_phrase}}, and I’m actively looking for opportunities as a <strong>{{target_role}}</strong>{% if company_display %} at <strong>{{company_display}}</strong>{% endif %}.</p>

<p><strong>A quick snapshot of my profile:</strong></p>

<ul>
  <li>{{achievement_1}}</li>
  <li>{{achievement_2}}</li>
  <li>{{achievement_3}}</li>
</ul>

<p>I’m reaching out in case there’s a suitable opening within your organization, either now or in the near future. If you feel my profile could be a good fit, I’d be grateful if you could consider my application.</p>

<p>{% if resume_attached %}I’ve attached my resume for your reference. {% endif %}You can also review my open-source projects on <a href="{{github_url}}">GitHub</a>{% if portfolio_url %} and my <a href="{{portfolio_url}}">Portfolio</a>{% endif %}.</p>

<p>Thank you for your time. I truly appreciate it, and I hope to hear from you if there’s an opportunity that matches my background.</p>

<div class="signature">
  <strong>{{my_name}}</strong><br>
  {% if contact_phone %}{{contact_phone}}<br>{% endif %}
  <a href="{{linkedin_url}}">LinkedIn</a> | <a href="{{github_url}}">GitHub</a>{% if portfolio_url %} | <a href="{{portfolio_url}}">Portfolio</a>{% endif %}
</div>

<div class="footer">
  If you would prefer not to receive future emails from me, simply reply with "unsubscribe" and I will immediately update my records.
</div>
</body>
</html>
"""
    },
    "aiml": {
        "name": "AI/ML & Data Engineering Focus",
        "description": "Tailored for AI, Machine Learning, Data Science, and Computer Vision roles",
        "subject_formats": [
            "Application: AI/ML & Software Engineering Roles – {{my_name}}",
            "Exploring AI/ML & Engineering Opportunities at {{company_display}} – {{my_name}}",
            "B.Tech CS Student – AI/ML Internship Inquiry ({{my_name}})"
        ],
        "text_body": """Dear {{salutation}},

I hope you are having a productive week.

I am writing to express my strong interest in AI/ML, Data Engineering, and Software Engineering internship or entry-level opportunities at {{company_display}}.

I am a {{my_degree}} student (Class of {{grad_year}}), passionate about building scalable intelligent systems. Through my academic and practical project work, I have gained hands-on experience in:
- Developing and evaluating Machine Learning and Deep Learning models using Python and modern ML frameworks.
- Building robust data pipelines and integrating predictive components into full-stack applications.
- Applying core Computer Science fundamentals (Data Structures, Algorithms, and System Design) to solve engineering problems.

I have followed the exciting work being done at {{company_display}} and would love the opportunity to contribute to your engineering initiatives while learning from your experienced team.

You can explore my projects and code on GitHub ({{github_url}}) and view my background on LinkedIn ({{linkedin_url}}).{% if resume_attached %} I have also attached my resume for your review.{% endif %}

Could you let me know if there are any openings or if you would be open to a brief 10-minute conversation?

Thank you very much for your time and consideration.

Warm regards,

{{my_name}}
{{my_degree}}
GitHub: {{github_url}}
LinkedIn: {{linkedin_url}}
{% if portfolio_url %}Portfolio: {{portfolio_url}}{% endif %}

---
If you prefer not to receive future emails from me, simply reply with 'unsubscribe' and I will promptly update my records.
""",
        "html_body": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #222222; }
  p { margin: 0 0 14px 0; }
  ul { margin: 0 0 14px 0; padding-left: 20px; }
  li { margin-bottom: 6px; }
  a { color: #1a73e8; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .signature { margin-top: 20px; border-top: 1px solid #e0e0e0; padding-top: 12px; color: #444; }
  .footer { margin-top: 25px; font-size: 11px; color: #888888; }
</style>
</head>
<body>
<p>Dear {{salutation}},</p>

<p>I hope you are having a productive week.</p>

<p>I am writing to express my strong interest in <strong>AI/ML, Data Engineering, and Software Engineering</strong> internship or entry-level opportunities at <strong>{{company_display}}</strong>.</p>

<p>I am a {{my_degree}} student (Class of {{grad_year}}), passionate about building scalable, intelligent systems. Through my coursework and practical project work, I have focused on:</p>

<ul>
  <li>Developing and deploying Machine Learning and Deep Learning models using Python and modern frameworks.</li>
  <li>Building robust data pipelines, REST APIs, and integrating predictive intelligence into software applications.</li>
  <li>Applying core Computer Science fundamentals (Data Structures, Algorithms, and System Architecture) to optimize performance.</li>
</ul>

<p>I have been closely following the impactful engineering work at {{company_display}} and would be thrilled to contribute to your team's initiatives while learning from your engineers.</p>

<p>You can review my projects and source code on <a href="{{github_url}}">GitHub</a> and connect with me on <a href="{{linkedin_url}}">LinkedIn</a>{% if portfolio_url %} or view my <a href="{{portfolio_url}}">Portfolio</a>{% endif %}.{% if resume_attached %} My resume is also attached for your convenience.{% endif %}</p>

<p>Could you let me know if you have any open roles or if you would be open to a brief 10-minute introductory call?</p>

<p>Thank you very much for your time and consideration.</p>

<div class="signature">
  <strong>{{my_name}}</strong><br>
  {{my_degree}}<br>
  <a href="{{github_url}}">GitHub</a> | <a href="{{linkedin_url}}">LinkedIn</a>{% if portfolio_url %} | <a href="{{portfolio_url}}">Portfolio</a>{% endif %}
</div>

<div class="footer">
  If you would prefer not to receive future emails from me, simply reply with "unsubscribe" and I will immediately update my records.
</div>
</body>
</html>
"""
    },
    "swe": {
        "name": "Software Engineering / Full-Stack Focus",
        "description": "Tailored for Software Development Engineer (SDE), Backend, and Full-Stack roles",
        "subject_formats": [
            "Application: Software Engineering Opportunities at {{company_display}} – {{my_name}}",
            "B.Tech CS Student – Software Engineering Internship Inquiry ({{my_name}})",
            "Exploring SDE & Engineering Roles at {{company_display}} – {{my_name}}"
        ],
        "text_body": """Dear {{salutation}},

I hope this email finds you well.

I am writing to explore potential Software Engineering (SDE) internship or entry-level opportunities at {{company_display}}.

I am currently pursuing my {{my_degree}} (Graduation: {{grad_year}}). My academic training and technical projects have given me a solid foundation in software development, including:
- Strong problem-solving abilities and algorithmic thinking with core Data Structures.
- Hands-on experience developing web applications, RESTful APIs, and backend services.
- Version control (Git), clean code practices, testing, and system design fundamentals.

I admire {{company_display}}'s engineering culture and high-impact products, and I would welcome the chance to bring my strong work ethic and technical curiosity to your development team.

Please feel free to check out my open-source projects on GitHub ({{github_url}}) and my professional background on LinkedIn ({{linkedin_url}}).{% if resume_attached %} I have also attached my resume.{% endif %}

Are you available for a brief conversation this week or next to discuss how I might contribute to your team?

Thank you for your consideration.

Warm regards,

{{my_name}}
{{my_degree}}
GitHub: {{github_url}}
LinkedIn: {{linkedin_url}}
{% if portfolio_url %}Portfolio: {{portfolio_url}}{% endif %}

---
If you prefer not to receive future emails from me, simply reply with 'unsubscribe' and I will promptly update my records.
""",
        "html_body": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #222222; }
  p { margin: 0 0 14px 0; }
  ul { margin: 0 0 14px 0; padding-left: 20px; }
  li { margin-bottom: 6px; }
  a { color: #1a73e8; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .signature { margin-top: 20px; border-top: 1px solid #e0e0e0; padding-top: 12px; color: #444; }
  .footer { margin-top: 25px; font-size: 11px; color: #888888; }
</style>
</head>
<body>
<p>Dear {{salutation}},</p>

<p>I hope this email finds you well.</p>

<p>I am writing to explore potential <strong>Software Engineering (SDE)</strong> internship or entry-level opportunities at <strong>{{company_display}}</strong>.</p>

<p>I am currently pursuing my {{my_degree}} (Graduation: {{grad_year}}). My academic training and hands-on projects have built a strong foundation in core software engineering:</p>

<ul>
  <li>Solid analytical problem-solving and algorithmic thinking in core Data Structures and Algorithms.</li>
  <li>Hands-on experience developing robust web applications, modular APIs, and database integrations.</li>
  <li>Proficiency in Git version control, unit testing, and maintainable software architecture.</li>
</ul>

<p>I admire {{company_display}}'s engineering standard and product innovation, and I would love the opportunity to contribute to your technical goals while growing alongside your engineering team.</p>

<p>Please feel free to explore my source code on <a href="{{github_url}}">GitHub</a> and review my background on <a href="{{linkedin_url}}">LinkedIn</a>{% if portfolio_url %} or <a href="{{portfolio_url}}">Portfolio</a>{% endif %}.{% if resume_attached %} My resume is also attached.{% endif %}</p>

<p>Could you let me know if your team has any current openings or if you would be open to a brief introductory conversation?</p>

<p>Thank you very much for your time and consideration.</p>

<div class="signature">
  <strong>{{my_name}}</strong><br>
  {{my_degree}}<br>
  <a href="{{github_url}}">GitHub</a> | <a href="{{linkedin_url}}">LinkedIn</a>{% if portfolio_url %} | <a href="{{portfolio_url}}">Portfolio</a>{% endif %}
</div>

<div class="footer">
  If you would prefer not to receive future emails from me, simply reply with "unsubscribe" and I will immediately update my records.
</div>
</body>
</html>
"""
    },
    "general": {
        "name": "General Computer Science & Engineering Focus",
        "description": "Versatile pitch covering both AI/ML and Software Engineering",
        "subject_formats": [
            "B.Tech CS Student – Exploring Internship & Entry-Level Roles at {{company_display}}",
            "Application: Technology & Engineering Opportunities – {{my_name}}",
            "Inquiry: Engineering Internships at {{company_display}} – {{my_name}}"
        ],
        "text_body": """Dear {{salutation}},

I hope you are having a wonderful week.

I am writing to inquire about upcoming internship and entry-level technology opportunities at {{company_display}}.

As a {{my_degree}} student (graduating in {{grad_year}}), I have focused on both core Software Engineering and applied AI/ML. My experience includes developing scalable code, building full-stack applications, and working with data-driven machine learning algorithms.

I am deeply impressed by the technical vision at {{company_display}}, and I am eager to apply my technical skills, fast learning pace, and problem-solving drive to your engineering initiatives.

You can view my code and projects on GitHub ({{github_url}}) and learn more about my background on LinkedIn ({{linkedin_url}}).{% if resume_attached %} My resume is also attached for your reference.{% endif %}

I would welcome the opportunity to discuss any potential openings or how I can add value to your team. Would you be open to a brief chat sometime soon?

Thank you for your time and guidance.

Warm regards,

{{my_name}}
{{my_degree}}
GitHub: {{github_url}}
LinkedIn: {{linkedin_url}}
{% if portfolio_url %}Portfolio: {{portfolio_url}}{% endif %}

---
If you prefer not to receive future emails from me, simply reply with 'unsubscribe' and I will promptly update my records.
""",
        "html_body": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #222222; }
  p { margin: 0 0 14px 0; }
  a { color: #1a73e8; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .signature { margin-top: 20px; border-top: 1px solid #e0e0e0; padding-top: 12px; color: #444; }
  .footer { margin-top: 25px; font-size: 11px; color: #888888; }
</style>
</head>
<body>
<p>Dear {{salutation}},</p>

<p>I hope you are having a wonderful week.</p>

<p>I am writing to inquire about upcoming <strong>internship and entry-level technology opportunities</strong> at <strong>{{company_display}}</strong>.</p>

<p>As a {{my_degree}} student (graduating in {{grad_year}}), I have built a versatile foundation in both Software Engineering and applied AI/ML. My hands-on work includes developing scalable applications, RESTful services, and exploring data-driven machine learning models.</p>

<p>I am deeply impressed by the technical standard at {{company_display}}, and I am eager to contribute my technical foundation, fast learning agility, and drive to your team's upcoming projects.</p>

<p>You can inspect my open projects on <a href="{{github_url}}">GitHub</a> and review my experience on <a href="{{linkedin_url}}">LinkedIn</a>{% if portfolio_url %} or my <a href="{{portfolio_url}}">Portfolio</a>{% endif %}.{% if resume_attached %} My resume is also attached.{% endif %}</p>

<p>I would welcome the opportunity to discuss any potential openings or how I might add value to your organization. Could you let me know if you would be open to a brief introductory chat?</p>

<p>Thank you very much for your time and guidance.</p>

<div class="signature">
  <strong>{{my_name}}</strong><br>
  {{my_degree}}<br>
  <a href="{{github_url}}">GitHub</a> | <a href="{{linkedin_url}}">LinkedIn</a>{% if portfolio_url %} | <a href="{{portfolio_url}}">Portfolio</a>{% endif %}
</div>

<div class="footer">
  If you would prefer not to receive future emails from me, simply reply with "unsubscribe" and I will immediately update my records.
</div>
</body>
</html>
"""
    }
}


class TemplateEngine:
    """Manages email templates, variable rendering, subject rotation, and spam auditing."""

    def __init__(self, user_profile: Any):
        self.profile = user_profile
        self.jinja_env = jinja2.Environment(autoescape=True)

    def _clean_str(self, val: Any) -> str:
        if val is None or pd.isna(val):
            return ""
        return str(val).strip()

    def determine_salutation(self, first_name: Any, company: Any) -> str:
        """Construct natural salutation based on available contact metadata."""
        fn = self._clean_str(first_name)
        co = self._clean_str(company)
        if fn:
            return fn
        elif co:
            return f"{co} Team"
        else:
            return "Hiring Team"

    def select_template_key(self, role_str: Any = "", default: str = "custom") -> str:
        """Select best template - defaults to user's custom template."""
        return default

    def render(
        self,
        contact: Dict[str, Any],
        template_key: Optional[str] = None,
        subject_index: int = 0
    ) -> Dict[str, Any]:
        """
        Render subject, plain text body, and HTML body for a given contact record.
        """
        role_title = self._clean_str(contact.get("job_title"))
        chosen_key = template_key or self.select_template_key(role_title)
        tmpl_config = TEMPLATES.get(chosen_key, TEMPLATES["custom"])

        raw_co = contact.get("cleaned_company") or contact.get("company")
        company_clean = self._clean_str(raw_co)
        company_display = company_clean if company_clean else "your team"

        first_name = self._clean_str(contact.get("first_name"))
        salutation = self.determine_salutation(first_name, company_clean)

        context = {
            "my_name": self._clean_str(self.profile.full_name),
            "my_degree": self._clean_str(self.profile.degree),
            "grad_year": self._clean_str(self.profile.grad_year),
            "current_designation": getattr(self.profile, "current_designation", "B.Tech Computer Science Student"),
            "experience_phrase": getattr(self.profile, "experience_phrase", "hands-on project experience in AI/ML and Software Engineering"),
            "target_role": getattr(self.profile, "target_role", "Software Engineering / AI-ML Intern"),
            "achievement_1": getattr(self.profile, "achievement_1", "Strong foundational expertise in Data Structures, Algorithms, and scalable software development"),
            "achievement_2": getattr(self.profile, "achievement_2", "Hands-on experience building ML/Deep Learning models and end-to-end data pipelines in Python"),
            "achievement_3": getattr(self.profile, "achievement_3", "Active open-source projects showcased on GitHub and personal web portfolio"),
            "contact_phone": getattr(self.profile, "contact_phone", None),
            "github_url": self._clean_str(self.profile.github_url),
            "linkedin_url": self._clean_str(self.profile.linkedin_url),
            "portfolio_url": self._clean_str(self.profile.portfolio_url) if self.profile.portfolio_url else None,
            "salutation": salutation,
            "company_display": company_display,
            "recruiter_name": self._clean_str(contact.get("cleaned_name")),
            "recruiter_title": role_title,
            "recipient_email": self._clean_str(contact.get("email")),
            "resume_attached": bool(self.profile.resume_path and self.profile.resume_path.exists())
        }

        # Subject line rotation
        subjects = tmpl_config["subject_formats"]
        chosen_subject_fmt = subjects[subject_index % len(subjects)]
        rendered_subject = jinja2.Template(chosen_subject_fmt).render(context)

        # Render plain text and HTML
        text_body = jinja2.Template(tmpl_config["text_body"]).render(context)
        html_body = jinja2.Template(tmpl_config["html_body"]).render(context)

        # Spam audit
        spam_warnings = self.audit_spam(rendered_subject, text_body)

        return {
            "template_key": chosen_key,
            "template_name": tmpl_config["name"],
            "subject": rendered_subject,
            "text_body": text_body,
            "html_body": html_body,
            "context": context,
            "spam_warnings": spam_warnings
        }

    def audit_spam(self, subject: str, body: str) -> list:
        """Check for common spam triggers."""
        warnings = []
        combined = f"{subject} {body}".lower()
        for word in SPAM_TRIGGER_WORDS:
            if word in combined:
                warnings.append(f"Detected spam-trigger word: '{word}'")
        
        if subject.isupper():
            warnings.append("Subject is all capital letters")
        
        if "!!!" in subject:
            warnings.append("Subject contains excessive punctuation")
            
        return warnings
