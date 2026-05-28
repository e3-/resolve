import data_utils as du


def create_project(
    project_name: str,
    project_category: du.ProjectCategories,
) -> du.Catalog:
    """Create a new project in the datalake.

    Registers a new project with the given name and category in the datalake
    catalog via DVC.

    Args:
        project_name: Name of the project to create.
        project_category: Category of the project (du.ProjectCategories).

    Returns:
        The project catalog object for the newly created project.

    Example:
        >>> create_project("my_project", du.ProjectCategories.RECAP)
    """
    project_catalog = du.Catalog.new_project(
        project_name=project_name,
        project_category=project_category,
    )
    print(f"Project {project_name} created successfully.")

    return project_catalog


if __name__ == "__main__":
    du.aws_sign_in()

    # Example usage
    project_name = "testing_kit_datalake"
    create_project(project_name, du.ProjectCategories.RECAP)
