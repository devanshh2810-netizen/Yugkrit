"""YugKrit - University dashboard routes."""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database.database import db
from database.models import (
    Challenge, University, Project, Faculty, StudentProfile, UniversityApplication,
    ChallengeCategory, Milestone
)
from utils.decorators import role_required, get_current_user
from services import project_service

university_bp = Blueprint("university", __name__, template_folder="../templates/university")

UNI_ROLES = ("UNIVERSITY_ADMIN", "FACULTY")


def _current_university():
    user = get_current_user()
    if not user or not user.organization:
        return None
    return University.query.filter_by(organization_id=user.organization_id).first()


@university_bp.route("/")
@role_required(*UNI_ROLES)
def overview():
    university = _current_university()
    stats = {
        "challenges_available": Challenge.query.filter_by(status="VERIFIED").count(),
        "active_projects": Project.query.filter_by(university_id=university.id)
                            .filter(Project.status.in_(["PLANNING", "IN_PROGRESS"])).count() if university else 0,
        "students": StudentProfile.query.filter_by(institution_id=university.id).count() if university else 0,
        "faculty": Faculty.query.filter_by(university_id=university.id).count() if university else 0,
        "pending_reviews": Milestone.query.join(Project).filter(
            Project.university_id == university.id, Milestone.status == "SUBMITTED"
        ).count() if university else 0,
        "completed_projects": Project.query.filter_by(university_id=university.id)
                               .filter(Project.status.in_(["COMPLETED", "VERIFIED"])).count() if university else 0,
    }
    my_projects = Project.query.filter_by(university_id=university.id).order_by(
        Project.created_at.desc()).limit(5).all() if university else []
    return render_template("university/overview.html", university=university, stats=stats, my_projects=my_projects)


@university_bp.route("/marketplace")
@role_required(*UNI_ROLES)
def marketplace():
    q = Challenge.query.filter_by(status="VERIFIED")
    category = request.args.get("category")
    district = request.args.get("district")
    if category:
        q = q.join(ChallengeCategory).filter(ChallengeCategory.name == category)
    if district:
        q = q.join(Challenge.location).filter_by(district=district)
    challenges = q.order_by(Challenge.priority_score.desc()).all()
    categories = ChallengeCategory.query.all()
    return render_template("university/marketplace.html", challenges=challenges, categories=categories)


@university_bp.route("/challenges/<int:challenge_id>")
@role_required(*UNI_ROLES)
def challenge_detail(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    university = _current_university()
    existing_application = UniversityApplication.query.filter_by(
        challenge_id=challenge_id, university_id=university.id).first() if university else None
    return render_template("university/challenge_detail.html", challenge=challenge,
                            existing_application=existing_application)


@university_bp.route("/challenges/<int:challenge_id>/apply", methods=["POST"])
@role_required(*UNI_ROLES)
def apply_challenge(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    university = _current_university()
    user = get_current_user()
    application = UniversityApplication(challenge_id=challenge.id, university_id=university.id,
                                          applied_by_id=user.id, pitch=request.form.get("pitch"))
    db.session.add(application)
    db.session.commit()
    flash("Application submitted for this challenge.", "success")
    return redirect(url_for("university.challenge_detail", challenge_id=challenge_id))


@university_bp.route("/projects")
@role_required(*UNI_ROLES)
def projects():
    university = _current_university()
    project_list = Project.query.filter_by(university_id=university.id).order_by(
        Project.created_at.desc()).all() if university else []
    return render_template("university/projects.html", projects=project_list)


@university_bp.route("/challenges/<int:challenge_id>/create-project", methods=["GET", "POST"])
@role_required("UNIVERSITY_ADMIN")
def create_project(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    university = _current_university()
    faculty_list = Faculty.query.filter_by(university_id=university.id).all()

    if request.method == "POST":
        f = request.form
        faculty = Faculty.query.get(f.get("faculty_mentor_id")) if f.get("faculty_mentor_id") else None
        data = {
            "name": f["name"], "objective": f.get("objective"), "description": f.get("description"),
            "expected_outcome": f.get("expected_outcome"),
            "start_date": datetime.strptime(f["start_date"], "%Y-%m-%d").date() if f.get("start_date") else None,
            "expected_completion": datetime.strptime(f["expected_completion"], "%Y-%m-%d").date()
                                    if f.get("expected_completion") else None,
        }
        project = project_service.create_project(challenge, university, faculty, data)
        flash("Project created. Now build your team.", "success")
        return redirect(url_for("university.project_workspace", project_id=project.id, tab="team"))

    return render_template("university/create_project.html", challenge=challenge, faculty_list=faculty_list)


@university_bp.route("/projects/<int:project_id>")
@role_required(*UNI_ROLES)
def project_workspace(project_id):
    project = Project.query.get_or_404(project_id)
    tab = request.args.get("tab", "overview")
    return render_template("university/project_workspace.html", project=project, tab=tab)


@university_bp.route("/projects/<int:project_id>/team", methods=["POST"])
@role_required("UNIVERSITY_ADMIN")
def add_team(project_id):
    project = Project.query.get_or_404(project_id)
    f = request.form
    names = f.getlist("member_name[]")
    emails = f.getlist("member_email[]")
    regnos = f.getlist("member_regno[]")
    roles = f.getlist("member_role[]")
    members = []
    for i in range(len(names)):
        if names[i].strip():
            members.append({"full_name": names[i], "college_email": emails[i],
                             "registration_number": regnos[i], "role_in_team": roles[i] or "Developer"})
    try:
        team, new_count = project_service.create_team(project, f.get("team_name", "Project Team"), members)
        flash(f"Team created with {len(members)} member(s) ({new_count} new invitation(s) sent).", "success")
    except Exception as e:
        flash(f"Could not create team: {e}", "danger")
    return redirect(url_for("university.project_workspace", project_id=project_id, tab="team"))


@university_bp.route("/milestones/<int:milestone_id>/update", methods=["POST"])
@role_required(*UNI_ROLES)
def update_milestone(milestone_id):
    milestone = Milestone.query.get_or_404(milestone_id)
    new_status = request.form.get("status")
    comment = request.form.get("comment")
    project_service.update_milestone_status(milestone, new_status, comment=comment, actor=get_current_user())
    flash("Milestone updated.", "success")
    return redirect(url_for("university.project_workspace", project_id=milestone.project_id, tab="milestones"))


@university_bp.route("/students")
@role_required(*UNI_ROLES)
def students():
    university = _current_university()
    student_list = StudentProfile.query.filter_by(institution_id=university.id).all() if university else []
    return render_template("university/students.html", students=student_list)


@university_bp.route("/faculty")
@role_required("UNIVERSITY_ADMIN")
def faculty():
    university = _current_university()
    faculty_list = Faculty.query.filter_by(university_id=university.id).all() if university else []
    return render_template("university/faculty.html", faculty_list=faculty_list)


@university_bp.route("/analytics")
@role_required(*UNI_ROLES)
def analytics():
    university = _current_university()
    projects = Project.query.filter_by(university_id=university.id).all() if university else []
    return render_template("university/analytics.html", projects=projects)
