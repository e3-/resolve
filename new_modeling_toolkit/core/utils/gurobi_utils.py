import os
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from loguru import logger

_GUROBI_API_BASE_URL = "https://cloud.gurobi.com/api/v2"
_GUROBI_API_ACCESS_ID_HEADER_PARAM_NAME = "X-GUROBI-ACCESS-ID"  # nosec
_GUROBI_API_SECRET_KEY_HEADER_PARAM_NAME = "X-GUROBI-SECRET-KEY"  # nosec

_GUROBI_LICENSE_CLOUDACCESSID_VARIABLE_NAME = "CLOUDACCESSID"
_GUROBI_LICENSE_CLOUDKEY_VARIABLE_NAME = "CLOUDKEY"
_GUROBI_LICENSE_LICENSEID_VARIABLE_NAME = "LICENSEID"
_GUROBI_LICENSE_CLOUDPOOL_VARIABLE_NAME = "CLOUDPOOL"

GUROBI_SOLVER_LICENSE_ENVIRONMENT_VARIABLE = "GRB_LICENSE_FILE"


def set_license_file_environment_variable(path_to_license: os.PathLike):
    os.environ[GUROBI_SOLVER_LICENSE_ENVIRONMENT_VARIABLE] = str(path_to_license)


@dataclass
class GurobiCredentials:
    """Dataclass for storing Gurobi Instant Cloud credentials."""

    cloud_access_id: str
    secret_key: str
    license_id: str
    pool_id: Optional[str] = None
    license_path: Optional[os.PathLike] = None

    @classmethod
    def from_license_file(cls, license_path: os.PathLike):
        """Create a set of credentials from a downloaded Gurobi Instant Cloud license.

        Args:
            license_path: path to the license file

        Returns:
            instance: instantiated credentials
        """
        with open(license_path, "r") as f:
            license_raw = f.readlines()

        license_filtered = [line.strip().split("=") for line in license_raw if not line.startswith("#")]
        license_variables = {key: val for key, val in license_filtered}

        instance = cls(
            license_path=license_path,
            cloud_access_id=license_variables.get(_GUROBI_LICENSE_CLOUDACCESSID_VARIABLE_NAME, None),
            secret_key=license_variables.get(_GUROBI_LICENSE_CLOUDKEY_VARIABLE_NAME, None),
            license_id=license_variables.get(_GUROBI_LICENSE_LICENSEID_VARIABLE_NAME, None),
            pool_id=license_variables.get(_GUROBI_LICENSE_CLOUDPOOL_VARIABLE_NAME, None),
        )

        return instance

    def start_pool(self, wait_time_seconds: int = 180) -> bool:
        """Sends an API request to start the instances in the desired pool represented by these credentials.

        Note that even if `wait_time_seconds` is exceeded and the method returns `False`, the pool *should* still
        eventually start up and may just be taking longer than expected. If, for example, you are running a large
        RESOLVE model that takes several minutes to compile, you could call this method with a short wait time and
        allow the pool to continue starting up while your model compiles. The default of three minutes should generally
        be long enough for the pool to start.

        Args:
            wait_time_seconds: how long to wait for the pool to start before exiting the function.

        Returns:
            pool_ready: whether the pool is ready and idle after the wait time has passed
        """
        # Create the API request URL
        request_url = f"{_GUROBI_API_BASE_URL}/pools/{self.pool_id}/machines"

        logger.debug(f"Starting Gurobi pool `{self.pool_id}`...")
        start_time = time.time()
        pool_ready = False

        while not pool_ready:
            # Submit the request
            start_pool_post_response = requests.post(
                url=request_url,
                headers={
                    _GUROBI_API_ACCESS_ID_HEADER_PARAM_NAME: self.cloud_access_id,
                    _GUROBI_API_SECRET_KEY_HEADER_PARAM_NAME: self.secret_key,
                },
            )

            # Raise an error if an unexpected error is returned by the request
            start_pool_post_response.raise_for_status()

            # Check if the pool is ready
            # Note: this POST request returns a 202 status code if the pool is in the process of starting up, and a 200
            #   status code if the pool is ready
            pool_ready = start_pool_post_response.status_code == 200
            if pool_ready:
                break
            end_time = time.time()
            if end_time - start_time > wait_time_seconds:
                logger.warning(f"Starting Gurobi pool exceeded specified wait time of `{wait_time_seconds}` seconds.")
                break
            time.sleep(2)

        return pool_ready

    def create_pool(
        self,
        machine_type: Optional[str] = None,
        num_instances: int = 1,
        job_limit: int = 1,
        num_distributed_workers: int = 0,
    ):
        """Creates a new Gurobi Cloud pool using the Pool ID specified in `self.pool_id`.

        Args:
            machine_type: AWS EC2 instance type to create in the pool
            num_instances: number of EC2 instances to create in the pool
            job_limit: maximum number of jobs that can be run on a single instance (not the entire pool)
            num_distributed_workers: max number of distributed workers on a single instance. Only relevant if a
                distributed algorithm is used.

        Returns:
            the pool ID of the created pool.

        Raises:
            ValueError: if the API request to create the pool is invalid
        """
        request_url = f"{_GUROBI_API_BASE_URL}/pools"

        request_params = {
            "name": self.pool_id,
            "machineType": machine_type,
            "nbComputeServers": num_instances,
            "nbDistributedWorkers": num_distributed_workers,
            "jobLimit": job_limit,
            "jobHistory": True,
            "idleShutdown": 20,
        }
        request_params = {key: val for key, val in request_params.items() if val is not None}

        create_pool_post_response = requests.post(
            url=request_url,
            headers={
                _GUROBI_API_ACCESS_ID_HEADER_PARAM_NAME: self.cloud_access_id,
                _GUROBI_API_SECRET_KEY_HEADER_PARAM_NAME: self.secret_key,
            },
            json=request_params,
        )

        if create_pool_post_response.status_code == 400:
            raise ValueError(
                f"GurobiCredentials.create_pool() request returned status code 400 with the following error: "
                f"\n\n {create_pool_post_response.json()}"
            )

        pool_id = re.findall("/api/v2/pools/(.*)", create_pool_post_response.headers["Location"])[0]

        return pool_id

    def check_if_pool_exists(self):
        """Checks if the pool ID associated with these credentials exists.

        Returns:
            whether the pool exists or not
        """
        request_url = f"{_GUROBI_API_BASE_URL}/pools/{self.pool_id}"
        get_pool_response = requests.get(
            request_url,
            headers={
                _GUROBI_API_ACCESS_ID_HEADER_PARAM_NAME: self.cloud_access_id,
                _GUROBI_API_SECRET_KEY_HEADER_PARAM_NAME: self.secret_key,
            },
        )

        pool_exists = get_pool_response.status_code == 200

        return pool_exists

    def scale_pool(self, num_instances: int):
        request_url = f"{_GUROBI_API_BASE_URL}/pools/{self.pool_id}/scaling"

        scale_pool_response = requests.post(
            request_url,
            params={"n": num_instances},
            headers={
                _GUROBI_API_ACCESS_ID_HEADER_PARAM_NAME: self.cloud_access_id,
                _GUROBI_API_SECRET_KEY_HEADER_PARAM_NAME: self.secret_key,
            },
        )

        scale_pool_response.raise_for_status()

    def to_license_file(self, output_path: os.PathLike):
        """Creates a license file that represents this credentials instance.

        This is currently used because Pyomo does not allow the user to specify which pool to use other than through
        a license file. In order to change what pool is being used, the Gurobi license environment variable must be
        modified to point to a license file that contains the desired Pool ID.

        Args:
            output_path: path to write the license file
        """
        output_lines = {
            _GUROBI_LICENSE_CLOUDACCESSID_VARIABLE_NAME: self.cloud_access_id,
            _GUROBI_LICENSE_CLOUDKEY_VARIABLE_NAME: self.secret_key,
            _GUROBI_LICENSE_LICENSEID_VARIABLE_NAME: self.license_id,
            _GUROBI_LICENSE_CLOUDPOOL_VARIABLE_NAME: self.pool_id,
        }
        with open(output_path, "w") as f:
            for key, val in output_lines.items():
                f.write(f"{key}={val}\n")
