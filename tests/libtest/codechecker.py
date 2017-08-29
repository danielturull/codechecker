# -----------------------------------------------------------------------------
#                     The CodeChecker Infrastructure
#   This file is distributed under the University of Illinois Open Source
#   License. See LICENSE.TXT for details.
# -----------------------------------------------------------------------------

import json
from libcodechecker import util
import os
import shlex
import stat
import subprocess
from subprocess import CalledProcessError
import time

from . import env
from . import project


def wait_for_postgres_shutdown(workspace):
    """
    Wait for PostgreSQL to shut down.
    Check if postmaster.pid file exists if yes postgres is still running.
    """
    max_wait_time = 60

    postmaster_pid_file = os.path.join(workspace,
                                       'pgsql_data',
                                       'postmaster.pid')

    while os.path.isfile(postmaster_pid_file):
        time.sleep(1)
        max_wait_time -= 1
        if max_wait_time == 0:
            break


def login(codechecker_cfg, test_project_path, username, password,
          protocol='http'):
    """
    Perform a command-line login to the server.
    """
    print("Logging in")
    port = str(codechecker_cfg['viewer_port'])
    login_cmd = ['CodeChecker', 'cmd', 'login', username,
                 '--verbose', 'debug',
                 '--url', protocol + '://' + 'localhost:' + port]

    auth_creds = {'client_autologin': True,
                  'credentials': {}}
    auth_file = os.path.join(test_project_path, ".codechecker.passwords.json")
    if not os.path.exists(auth_file):
        # Create a default authentication file for the user, which has
        # proper structure.
        with open(auth_file, 'w') as outfile:
            json.dump(auth_creds, outfile)
    else:
        with open(auth_file, 'r') as infile:
            auth_creds = json.load(infile)

    # Write the new credentials to the file and save it.
    auth_creds['credentials']['localhost:' + port] = username + ':' + password
    with open(auth_file, 'w') as outfile:
        json.dump(auth_creds, outfile)
        print("Added '" + username + ':' + password + "' to credentials file.")

    os.chmod(auth_file, stat.S_IRUSR | stat.S_IWUSR)

    try:
        print(' '.join(login_cmd))
        out = subprocess.call(shlex.split(' '.join(login_cmd)),
                              cwd=test_project_path,
                              env=codechecker_cfg['check_env'])
        print out
        return 0
    except OSError as cerr:
        print("Failed to call:\n" + ' '.join(login_cmd))
        print(str(cerr.errno) + ' ' + cerr.message)
        return cerr.errno


def logout(codechecker_cfg, test_project_path, protocol='http'):
    """
    Perform a command-line logout from a server. This method also clears the
    credentials assigned to the server.
    """
    print("Logging out")
    port = str(codechecker_cfg['viewer_port'])
    logout_cmd = ['CodeChecker', 'cmd', 'login',
                  '--logout',
                  '--verbose', 'debug',
                  '--url', protocol + '://'+'localhost:' + port]

    auth_file = os.path.join(test_project_path, ".codechecker.passwords.json")
    if os.path.exists(auth_file):
        # Remove the credentials associated with the throw-away test server.
        with open(auth_file, 'r') as infile:
            auth_creds = json.load(infile)

        try:
            del auth_creds['credentials']['localhost:' + port]

            with open(auth_file, 'w') as outfile:
                json.dump(auth_creds, outfile)
                print("Removed credentials from 'localhost:" + port + "'.")
        except KeyError:
            print("Didn't remove any credentials as none were present. "
                  "Did you login()?")
    else:
        print("Credentials file did not exist. Did you login()?")

    try:
        print(' '.join(logout_cmd))
        out = subprocess.call(shlex.split(' '.join(logout_cmd)),
                              cwd=test_project_path,
                              env=codechecker_cfg['check_env'])
        print out
        return 0
    except OSError as cerr:
        print("Failed to call:\n" + ' '.join(logout_cmd))
        print(str(cerr.errno) + ' ' + cerr.message)
        return cerr.errno


def check(codechecker_cfg, test_project_name, test_project_path):
    """
    Check a test project and store the results into the database.

    :checkers parameter should be a list of enabled or disabled checkers
    Example: ['-d', 'deadcode.DeadStores']

    """

    output_dir = codechecker_cfg['reportdir'] \
        if 'reportdir' in codechecker_cfg \
        else os.path.join(codechecker_cfg['workspace'], 'reports')

    build_cmd = project.get_build_cmd(test_project_path)

    check_cmd = ['CodeChecker', 'check',
                 '-o', output_dir,
                 '-b', "'" + build_cmd + "'",
                 '--analyzers', 'clangsa',
                 '--quiet',
                 '--verbose', 'debug']

    suppress_file = codechecker_cfg.get('suppress_file')
    if suppress_file:
        check_cmd.extend(['--suppress', suppress_file])

    skip_file = codechecker_cfg.get('skip_file')
    if skip_file:
        check_cmd.extend(['--skip', skip_file])

    force = codechecker_cfg.get('force')
    if force:
        check_cmd.extend(['--force'])

    check_cmd.extend(codechecker_cfg['checkers'])

    try:
        print("RUNNING CHECK")
        print(' '.join(check_cmd))
        proc = subprocess.call(shlex.split(' '.join(check_cmd)),
                               cwd=test_project_path,
                               env=codechecker_cfg['check_env'])

    except CalledProcessError as cerr:
        print("Failed to call:\n" + ' '.join(cerr.cmd))
        return cerr.returncode

    store_cmd = ['CodeChecker', 'store', '-n', test_project_name,
                 output_dir,
                 '--url', env.parts_to_url(codechecker_cfg),
                 '--verbose', 'debug']

    tag = codechecker_cfg.get('tag')
    if tag:
        store_cmd.extend(['--tag', tag])

    try:
        print("RUNNING STORE")
        print(' '.join(store_cmd))
        proc = subprocess.call(shlex.split(' '.join(store_cmd)),
                               cwd=test_project_path,
                               env=codechecker_cfg['check_env'])
        return 0

    except CalledProcessError as cerr:
        print("Failed to call:\n" + ' '.join(cerr.cmd))
        return cerr.returncode


def analyze(codechecker_cfg, test_project_name, test_project_path):
    """
    Analyze a test project.

    :checkers parameter should be a list of enabled or disabled checkers
    Example: ['-d', 'deadcode.DeadStores']

    """

    build_cmd = project.get_build_cmd(test_project_path)
    build_json = os.path.join(codechecker_cfg['workspace'], "build.json")

    log_cmd = ['CodeChecker', 'log',
               '-o', build_json,
               '-b', "'" + build_cmd + "'",
               ]

    analyze_cmd = ['CodeChecker', 'analyze',
                   build_json,
                   '-o', codechecker_cfg['reportdir'],
                   '--analyzers', 'clangsa'
                   ]

    analyze_cmd.extend(codechecker_cfg['checkers'])
    try:
        print("LOG:")
        proc = subprocess.Popen(shlex.split(' '.join(log_cmd)),
                                cwd=test_project_path,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=codechecker_cfg['check_env'])
        out, err = proc.communicate()
        print(out)
        print(err)

        print("ANALYZE:")
        print(shlex.split(' '.join(analyze_cmd)))
        proc = subprocess.Popen(shlex.split(' '.join(analyze_cmd)),
                                cwd=test_project_path,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=codechecker_cfg['check_env'])
        out, err = proc.communicate()
        print(out)
        print(err)
        return 0
    except CalledProcessError as cerr:
        print("Failed to call:\n" + ' '.join(cerr.cmd))
        return cerr.returncode


def store(codechecker_cfg, test_project_name, report_path):
    """
    Store results from a report dir.
    """

    store_cmd = ['CodeChecker', 'store',
                 '--url', env.parts_to_url(codechecker_cfg),
                 '--name', test_project_name,
                 report_path]

    try:
        print("STORE:")
        proc = subprocess.Popen(shlex.split(' '.join(store_cmd)),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=codechecker_cfg['check_env'])
        out, err = proc.communicate()
        print(out)
        print(err)

        return 0
    except CalledProcessError as cerr:
        print("Failed to call:\n" + ' '.join(cerr.cmd))
        return cerr.returncode


def serv_cmd(config_dir, port, pg_config=None):

    server_cmd = ['CodeChecker', 'server',
                  '--config-directory', config_dir]

    server_cmd.extend(['--host', 'localhost',
                       '--port', str(port)])

    # server_cmd.extend(['--verbose', 'debug'])

    if pg_config:
        server_cmd.append('--postgresql')
        server_cmd += _pg_db_config_to_cmdline_params(pg_config)
    else:
        server_cmd += ['--sqlite', os.path.join(config_dir, 'config.sqlite')]

    print(' '.join(server_cmd))

    return server_cmd


def start_or_get_server():
    """
    Create a global CodeChecker server with the given configuration.
    """
    config_dir = env.get_workspace(None)
    portfile = os.path.join(config_dir, 'serverport')

    if os.path.exists(portfile):
        print("A server appears to be already running...")
        with open(portfile, 'r') as f:
            port = int(f.read())
    else:
        # Set up the root user and the authentication for the server.
        env.enable_auth(config_dir)

        port = env.get_free_port()
        print("Setting up CodeChecker server in " + config_dir + " :" +
              str(port))

        with open(portfile, 'w') as f:
            f.write(str(port))

        pg_config = env.get_postgresql_cfg()

        server_cmd = serv_cmd(config_dir, port, pg_config)

        print("Starting server...")
        subprocess.Popen(server_cmd, env=env.test_env(config_dir))

        # Wait for server to start and connect to database.
        # We give a bit of grace period here as a separate subcommand needs to
        # attach.
        time.sleep(5)

        if pg_config:
            # The behaviour is that CodeChecker servers only configure a
            # 'Default' product in SQLite mode, if the server was started
            # brand new. But certain test modules might make use of a
            # default product, so we now manually have to create it.
            print("PostgreSQL server does not create 'Default' product...")
            print("Creating it now!")
            default_path = os.path.join(config_dir, 'Default')
            os.makedirs(default_path)
            add_test_package_product({'viewer_host': 'localhost',
                                      'viewer_port': port,
                                      'viewer_product': 'Default'},
                                     default_path)
    return {
        'viewer_host': 'localhost',
        'viewer_port': port
    }


def add_test_package_product(server_data, test_folder, check_env=None,
                             protocol='http'):
    """
    Add a product for a test suite to the server provided by server_data.
    Server must be running before called.

    server_data must contain three keys: viewer_{host, port, product}.
    """

    if not check_env:
        check_env = env.test_env(test_folder)

    codechecker_cfg = {'check_env': check_env}
    codechecker_cfg.update(server_data)

    # Clean the previous session if any exists.
    logout(codechecker_cfg, test_folder, protocol)

    url = util.create_product_url(protocol, server_data['viewer_host'],
                                  str(server_data['viewer_port']),
                                  '')

    add_command = ['CodeChecker', 'cmd', 'products', 'add',
                   server_data['viewer_product'],
                   '--url', url,
                   '--name', os.path.basename(test_folder),
                   '--description', "Automatically created product for test."]

    # If tests are running on postgres, we need to create a database.
    pg_config = env.get_postgresql_cfg()
    if pg_config:
        env.add_database(server_data['viewer_product'], check_env)

        add_command.append('--postgresql')
        pg_config['dbname'] = server_data['viewer_product']
        add_command += _pg_db_config_to_cmdline_params(pg_config)
    else:
        # SQLite databases are put under the workspace of the appropriate test.
        add_command += ['--sqlite',
                        os.path.join(test_folder, 'data.sqlite')]

    print(' '.join(add_command))

    # Authenticate as SUPERUSER to be able to create the product.
    login(codechecker_cfg, test_folder, "root", "root", protocol)
    # The schema creation is a synchronous call.
    returncode = subprocess.call(add_command, env=check_env)
    logout(codechecker_cfg, test_folder, protocol)

    # After login as SUPERUSER, continue running the test as a normal user.
    # login() saves the relevant administrative file
    login(codechecker_cfg, test_folder, "cc", "test", protocol)

    if returncode:
        raise Exception("Failed to add the product to the test server!")


def remove_test_package_product(test_folder, check_env=None, protocol='http'):
    """
    Remove the product associated with the given test folder.
    The folder must exist, as the server configuration is read from the folder.
    """

    if not check_env:
        check_env = env.test_env(test_folder)

    server_data = env.import_test_cfg(test_folder)['codechecker_cfg']
    print(server_data)

    if 'check_env' not in server_data:
        server_data['check_env'] = check_env

    # Clean the previous session if any exists.
    logout(server_data, test_folder, protocol)
    url = util.create_product_url(protocol, server_data['viewer_host'],
                                  str(server_data['viewer_port']),
                                  '')
    del_command = ['CodeChecker', 'cmd', 'products', 'del',
                   server_data['viewer_product'],
                   '--url', url]

    print(' '.join(del_command))

    # Authenticate as SUPERUSER to be able to create the product.
    login(server_data, test_folder, "root", "root", protocol)
    returncode = subprocess.call(del_command, env=check_env)
    logout(server_data, test_folder, protocol)

    # If tests are running on postgres, we need to delete the database.
    # SQLite databases are deleted automatically as part of the
    # workspace removal.
    if env.get_postgresql_cfg():
        env.del_database(server_data['viewer_product'], check_env)

    if returncode:
        raise Exception("Failed to remove the product from the test server!")


def _pg_db_config_to_cmdline_params(pg_db_config):
    """Format postgres config dict to CodeChecker cmdline parameters."""
    params = []

    for key, value in pg_db_config.items():
        params.append('--' + key)
        params.append(str(value))

    return params
