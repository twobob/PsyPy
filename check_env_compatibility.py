import json
import subprocess
import sys
import os
from pathlib import Path
import configparser
import re
from packaging.requirements import Requirement, InvalidRequirement
from packaging.version import parse as parse_version, InvalidVersion
from packaging.specifiers import SpecifierSet, InvalidSpecifier

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Package name mapping between PyPI and Conda
CONDA_PYPI_MAP = {
    'opencv-python': 'opencv',
    'pyyaml': 'yaml',
    'pillow': 'pil',
    'scikit-learn': 'scikit-learn',
    'tensorflow-gpu': 'tensorflow-gpu',
    'torch': 'pytorch',
    'torchvision': 'pytorch-vision',
    'torchaudio': 'pytorch-audio'
}

# Config file for storing user preferences
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env_checker.ini")

def save_conda_path(conda_path):
    """Save conda path to local configuration file."""
    config = configparser.ConfigParser()
    
    # Read existing config if it exists
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
    
    # Create section if it doesn't exist
    if 'conda' not in config:
        config['conda'] = {}
    
    # Save the conda path
    config['conda']['path'] = conda_path
    
    # Write the config file
    try:
        with open(CONFIG_FILE, 'w') as f:
            config.write(f)
        print(f"{bcolors.OKGREEN}Saved conda path to {CONFIG_FILE}{bcolors.ENDC}")
    except IOError as e:
        print(f"{bcolors.WARNING}Could not save conda path to {CONFIG_FILE}: {e}{bcolors.ENDC}")


def load_conda_path():
    """Load conda path from local configuration file."""
    if not os.path.exists(CONFIG_FILE):
        return None
        
    config = configparser.ConfigParser()
    try:
        config.read(CONFIG_FILE)
        if 'conda' in config and 'path' in config['conda']:
            return config['conda']['path']
    except Exception as e:
        print(f"{bcolors.WARNING}Could not load conda path from {CONFIG_FILE}: {e}{bcolors.ENDC}")
    return None

def normalize_name(name, source='pypi'):
    """Standardize package names between PyPI and Conda."""
    return CONDA_PYPI_MAP.get(name.lower(), name.lower()) if source == 'conda' else name.lower()

def get_installed_packages(env_python_exe_path):
    """Retrieve installed packages and versions for a Python environment."""
    try:
        result = subprocess.run(
            [str(env_python_exe_path), "-m", "pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60
        )
        try:
            return {pkg["name"].lower(): pkg["version"] for pkg in json.loads(result.stdout)}
        except json.JSONDecodeError:
            pass
    except (subprocess.CalledProcessError, TimeoutError, FileNotFoundError):
        pass
        
    try:
        result = subprocess.run(
            [str(env_python_exe_path), "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60
        )
        packages = {}
        for line in result.stdout.splitlines(): 
            if '==' in line:
                parts = line.strip().split('==', 1)
                if len(parts) == 2: 
                     packages[parts[0].lower().strip()] = parts[1].strip()
        return packages
    except (subprocess.CalledProcessError, TimeoutError, FileNotFoundError): 
        print(f"{bcolors.WARNING}Warning: Could not get packages from {env_python_exe_path}{bcolors.ENDC}")
        return {}

def get_environment_python_version(python_exe_path_str):
    """Gets X.Y.Z or X.Y Python version string from a Python executable."""
    try:
        result = subprocess.run([str(python_exe_path_str), "--version"], capture_output=True, text=True, check=True, timeout=10) 
        output = result.stdout.strip() + " " + result.stderr.strip() 
        match = re.search(r"Python\s*(\d+\.\d+(?:\.\d+)?)", output) 
        if match:
            return match.group(1)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        pass
    return None


def parse_requirements_file(requirements_path): # Original name
    """Parse requirements.txt into structured package requirements."""
    requirements = [] 
    extra_urls = []   
    
    try: 
        with open(requirements_path, 'r', encoding='utf-8') as f: 
            for line_num, raw_line_content in enumerate(f, 1): 
                line = raw_line_content.strip()
                if not line or line.startswith(('#', '@EXPLICIT')):
                    continue
                    
                if line.startswith('--extra-index-url'):
                    extra_urls.append(line.split(None, 1)[-1])
                    continue
                    
                if line.startswith('--'): 
                    continue
                
                original_line_for_context = line 
                
                if any(url_protocol in line for url_protocol in ('http://', 'https://', 'git+')):
                    if '#egg=' in line:
                        egg_part = line.split('#egg=')[1].split('&')[0].strip()
                        name_str, version_str = (egg_part.split('==', 1) + [None])[:2] 
                        requirements.append({
                            'name': name_str.lower() if name_str else f"unnamed_url_pkg_{line_num}",
                            'specs': [{'operator': '==', 'version': version_str}] if version_str else [],
                            'marker': None,
                            'url': line,
                            'original': original_line_for_context 
                        })
                    continue
                
                try:
                    line_for_parsing_attempt = line.split('#')[0].strip()
                    if not line_for_parsing_attempt: continue 

                    req_parsed_object = Requirement(line_for_parsing_attempt)
                    requirements.append({
                        'name': req_parsed_object.name.lower(),
                        'specs': [{'operator': s.operator, 'version': s.version} for s in req_parsed_object.specifier],
                        'marker': req_parsed_object.marker,
                        'url': req_parsed_object.url, 
                        'original': original_line_for_context 
                    })
                except InvalidRequirement:
                    line_to_fallback_parse_on = line.split('#')[0].strip() 
                    
                    if '==' in line_to_fallback_parse_on:
                        parts = line_to_fallback_parse_on.split('==', 1)
                        name = parts[0].strip()
                        version = parts[1].split()[0].strip() if ' ' in parts[1] else parts[1].strip()
                        requirements.append({
                            'name': name.lower(),
                            'specs': [{'operator': '==', 'version': version}],
                            'marker': None, 'url': None, 'original': original_line_for_context
                        })
                    elif '>=' in line_to_fallback_parse_on:
                        parts = line_to_fallback_parse_on.split('>=', 1)
                        name = parts[0].strip(); version = parts[1].split()[0].strip() if ' ' in parts[1] else parts[1].strip()
                        requirements.append({
                            'name': name.lower(),
                            'specs': [{'operator': '>=', 'version': version}],
                            'marker': None, 'url': None, 'original': original_line_for_context
                        })
                    elif '<=' in line_to_fallback_parse_on:
                        parts = line_to_fallback_parse_on.split('<=', 1)
                        name = parts[0].strip(); version = parts[1].split()[0].strip() if ' ' in parts[1] else parts[1].strip()
                        requirements.append({
                            'name': name.lower(),
                            'specs': [{'operator': '<=', 'version': version}],
                            'marker': None, 'url': None, 'original': original_line_for_context
                        })
                    else: 
                        name = line_to_fallback_parse_on.split('[')[0].strip().split(' ')[0].strip() 
                        if name: 
                            requirements.append({
                                'name': name.lower(),
                                'specs': [], 'marker': None, 'url': None, 'original': original_line_for_context
                            })
                        else:
                            print(f"{bcolors.WARNING}Could not parse requirement (line {line_num}): {original_line_for_context}{bcolors.ENDC}")
    except FileNotFoundError:
         raise
    except Exception as e: 
        print(f"{bcolors.FAIL}Error reading or parsing requirements file {requirements_path}: {e}{bcolors.ENDC}")
        return [], [] 

    return requirements, extra_urls

def parse_single_requirement_string(requirement_str_input): # New function
    """Parse a single requirement string into the expected structure."""
    requirements_out_single = []
    
    line = requirement_str_input.strip()
    
    if not line or line.startswith(('#')): 
        return [], []

    original_input_str_ctx = requirement_str_input 

    if any(url_protocol in line for url_protocol in ('http://', 'https://', 'git+')):
        if '#egg=' in line:
            egg_part = line.split('#egg=')[1].split('&')[0].strip()
            name_str, version_str = (egg_part.split('==', 1) + [None])[:2]
            requirements_out_single.append({
                'name': name_str.lower() if name_str else "unnamed_url_pkg_single",
                'specs': [{'operator': '==', 'version': version_str}] if version_str else [],
                'marker': None, 'url': line, 'original': original_input_str_ctx
            })
        return requirements_out_single, [] 
    
    try:
        line_for_parsing_req = line.split('#')[0].strip()
        if not line_for_parsing_req: 
            return [], []

        req_parsed_obj_single = Requirement(line_for_parsing_req)
        requirements_out_single.append({
            'name': req_parsed_obj_single.name.lower(),
            'specs': [{'operator': s.operator, 'version': s.version} for s in req_parsed_obj_single.specifier],
            'marker': req_parsed_obj_single.marker,
            'url': req_parsed_obj_single.url,
            'original': original_input_str_ctx 
        })
    except InvalidRequirement:
        raise 
            
    return requirements_out_single, []


def find_conda_executable():
    """Locate conda executable with platform-specific paths and user input."""
    if saved_path := load_conda_path():
        if os.path.exists(saved_path): 
            try:
                result = subprocess.run(
                    [saved_path, "--version"],
                    capture_output=True, text=True, check=True, timeout=5
                )
                if result.returncode == 0:
                    print(f"Found conda from saved path: {saved_path}")
                    return saved_path
            except Exception: 
                print(f"{bcolors.WARNING}Warning: Saved conda path {saved_path} is invalid or non-functional{bcolors.ENDC}")
    
    if conda_exe_env := os.environ.get('CONDA_EXE'):
        try:
            result = subprocess.run([conda_exe_env, "--version"], capture_output=True, text=True, check=True, timeout=5)
            if result.returncode == 0:
                print(f"Found conda from CONDA_EXE: {conda_exe_env}")
                return conda_exe_env
        except Exception:
            print(f"{bcolors.WARNING}Warning: CONDA_EXE path {conda_exe_env} is invalid or non-functional{bcolors.ENDC}")

    windows_locations = [
        "conda", "conda.bat", 
        "C:/ProgramData/Anaconda3/Scripts/conda.exe", "C:/ProgramData/miniconda3/Scripts/conda.exe",
        str(Path.home() / "Anaconda3" / "Scripts" / "conda.exe"), str(Path.home() / "miniconda3" / "Scripts" / "conda.exe"),
        "C:/ProgramData/Anaconda3/condabin/conda.bat", "C:/ProgramData/miniconda3/condabin/conda.bat",
        str(Path.home() / "Anaconda3" / "condabin" / "conda.bat"), str(Path.home() / "miniconda3" / "condabin" / "conda.bat"),
        "C:/webui/installer_files/conda/condabin/conda.bat", "C:/webui/installer_files/conda/Scripts/conda.exe", 
        str(Path("C:/") / "Anaconda3" / "Scripts" / "conda.exe"), str(Path("C:/") / "Miniconda3" / "Scripts" / "conda.exe"),
        str(Path("D:/") / "Anaconda3" / "Scripts" / "conda.exe"), str(Path("D:/") / "Miniconda3" / "Scripts" / "conda.exe"),
    ]
    unix_locations = [
        "conda", 
        str(Path.home() / 'miniconda3' / 'bin' / 'conda'), str(Path.home() / 'anaconda3' / 'bin' / 'conda'),
        '/opt/conda/bin/conda', '/usr/local/anaconda3/bin/conda', '/usr/local/miniconda3/bin/conda',
    ]
    
    possible_locations = windows_locations if sys.platform == 'win32' else unix_locations
    
    for path_dir_str in os.environ.get("PATH", "").split(os.pathsep):
        path_dir = Path(path_dir_str)
        for conda_exe_name_path in (["conda.exe", "conda.bat", "conda"] if sys.platform == 'win32' else ["conda"]):
            conda_path_in_env_check = path_dir / conda_exe_name_path
            if conda_path_in_env_check.is_file(): 
                possible_locations.insert(0, str(conda_path_in_env_check))
    
    seen_paths_str_unique = set()
    unique_locations_list_str = []
    for loc_str_item in possible_locations:
        normalized_loc_str_item = os.path.normpath(loc_str_item)
        if normalized_loc_str_item not in seen_paths_str_unique:
            seen_paths_str_unique.add(normalized_loc_str_item)
            unique_locations_list_str.append(loc_str_item) 
    
    for location_to_test_str in unique_locations_list_str:
        try:
            for arg_to_test_with in ["--version", "info --json"]: 
                try:
                    cmd_parts_list = [location_to_test_str] + arg_to_test_with.split()
                    result_find = subprocess.run(
                        cmd_parts_list, capture_output=True, text=True, check=True, timeout=7
                    )
                    if result_find.returncode == 0:
                        if "--version" in arg_to_test_with and "conda version" in result_find.stdout.lower() or \
                           ("info" in arg_to_test_with and result_find.stdout.strip().startswith("{")):
                            print(f"Found conda at: {location_to_test_str}")
                            save_conda_path(location_to_test_str)
                            return location_to_test_str
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
                    continue 
        except Exception: 
            continue
    
    print(f"{bcolors.WARNING}Conda not found automatically in common locations or PATH.{bcolors.ENDC}") 
    
    user_provided_path_input = input(f"\n{bcolors.BOLD}Please enter the full path to your conda executable (or press Enter to skip):{bcolors.ENDC} ").strip()
    if user_provided_path_input:
        try:
            result_user = subprocess.run(
                [user_provided_path_input, "--version"], capture_output=True, text=True, check=True, timeout=5
            )
            if result_user.returncode == 0 and "conda version" in result_user.stdout.lower():
                print(f"{bcolors.OKGREEN}Successfully validated conda at: {user_provided_path_input}{bcolors.ENDC}")
                save_conda_path(user_provided_path_input)
                return user_provided_path_input
            else:
                print(f"{bcolors.FAIL}Error: The path '{user_provided_path_input}' did not respond like a valid conda executable.{bcolors.ENDC}")
        except Exception as e_user_path:
            print(f"{bcolors.FAIL}Error validating user-provided conda path '{user_provided_path_input}': {str(e_user_path)}{bcolors.ENDC}")
    
    return None

def get_conda_envs(conda_path): # Original name
    """List all conda environments with validation."""
    if not conda_path:
        return []
        
    try:
        result = subprocess.run(
            [conda_path, 'env', 'list', '--json'],
            capture_output=True, text=True, check=True, timeout=30
        )
        try:
            envs_data = json.loads(result.stdout)
            env_paths_str_list = envs_data.get('envs', [])
            if not env_paths_str_list and "conda_environments" in envs_data: 
                env_paths_str_list = [env_item[0] for env_item in envs_data["conda_environments"]]
                
            valid_envs_list = [Path(p_str_item).resolve() for p_str_item in env_paths_str_list if Path(p_str_item).is_dir()] 
            unique_valid_envs_list = list(dict.fromkeys(valid_envs_list))
            print(f"\nFound {len(unique_valid_envs_list)} unique valid conda environments (from {len(env_paths_str_list)} reported) using JSON.")
            return unique_valid_envs_list
        except json.JSONDecodeError:
            print(f"{bcolors.WARNING}Warning: Could not parse JSON from 'conda env list'. Falling back.{bcolors.ENDC}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e: 
        print(f"{bcolors.WARNING}Warning: 'conda env list --json' failed: {e}. Falling back.{bcolors.ENDC}")
        
    try:
        result = subprocess.run(
            [conda_path, 'env', 'list'],
            capture_output=True, text=True, check=True, timeout=30
        )
        
        envs_text_fallback = []
        for line_text_env in result.stdout.strip().split('\n'):
            if line_text_env.startswith('#') or not line_text_env.strip():
                continue
            parts_text_env = line_text_env.split()
            if len(parts_text_env) >= 2: 
                path_candidate_text_str = parts_text_env[-1]
                if Path(path_candidate_text_str).is_dir(): 
                    envs_text_fallback.append(Path(path_candidate_text_str).resolve()) 
        
        if envs_text_fallback:
            unique_envs_text_fallback = list(dict.fromkeys(envs_text_fallback)) 
            print(f"\nFound {len(unique_envs_text_fallback)} unique conda environments using text parsing.")
            return unique_envs_text_fallback
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e: 
        print(f"{bcolors.FAIL}Error: 'conda env list' (text mode) also failed: {e}{bcolors.ENDC}")
        
    return []

def check_version_compatibility(installed_version_str, specs_list, pkg_name=""): # Original name
    """Validate installed version against requirement specs."""
    if not specs_list: 
        return True
        
    try:
        installed_v_parsed = parse_version(installed_version_str) 
        
        # Special handling for PyTorch nightly builds (from original script)
        if installed_v_parsed.is_devrelease and any('dev' in s['version'] for s in specs_list if s['operator'] == '=='):
            for spec_item_dev in specs_list:
                if spec_item_dev['operator'] == '==' and 'dev' in spec_item_dev['version']:
                    required_dev_v_str = spec_item_dev['version']
                    try:
                        required_dev_v = parse_version(required_dev_v_str)
                        if installed_v_parsed.base_version.startswith(required_dev_v.base_version.rsplit('.', 1)[0]): 
                            return True
                    except InvalidVersion:
                        continue 
            return False 
        
        current_specs_to_use_for_comparison = []
        if pkg_name.lower() == "python":
            for s_item_py_spec in specs_list:
                if s_item_py_spec['operator'] == '==' and re.fullmatch(r"\d+\.\d+", s_item_py_spec['version']):
                    # If Python requirement is "==X.Y", treat as compatible release "~=X.Y"
                    # This means "==3.8" will match "3.8.0", "3.8.3", "3.8.10", etc.
                    current_specs_to_use_for_comparison.append({'operator': '~=', 'version': s_item_py_spec['version']})
                else:
                    current_specs_to_use_for_comparison.append(s_item_py_spec)
        else:
            current_specs_to_use_for_comparison = specs_list
        
        spec_str_list_combined_final = [f"{s_final_spec['operator']}{s_final_spec['version']}" for s_final_spec in current_specs_to_use_for_comparison]
        specifiers_set_obj_final = SpecifierSet(','.join(spec_str_list_combined_final))
        
        # Allow prereleases to be considered for matching, especially for Python versions or if spec implies it.
        # The `packaging` library's `contains` method default for prereleases depends on the specifier.
        # Explicitly setting prereleases=True ensures versions like "3.8.0rc1" can match ">=3.8.0"
        # if the spec doesn't explicitly forbid them (e.g. by not having a pre-release marker itself).
        # This was the effective behavior of packaging.SpecifierSet(...) in original script for some cases.
        return specifiers_set_obj_final.contains(installed_v_parsed, prereleases=True)

    except InvalidVersion: 
        for spec_item_fallback in specs_list:
            if spec_item_fallback['operator'] == '==' and installed_version_str == spec_item_fallback['version']:
                return True
        return False
    except InvalidSpecifier: 
        print(f"{bcolors.FAIL}Error: Invalid specifier string generated for {pkg_name}. Please check requirements format.{bcolors.ENDC}")
        return False


def evaluate_marker(marker, python_version, platform): # Original parameter names
    """Evaluate environment marker conditions."""
    if not marker: 
        return True
    
    try:
        eval_env = { # Original variable name
            'python_version': python_version, 
            'sys_platform': platform    
        }
        return marker.evaluate(environment=eval_env) # Original usage
    except Exception: # Original was broad Exception
        return True  


def analyze_environment(env_path, requirements, python_version, platform): # Original parameter names
    """Analyze package compatibility for a specific environment."""
    python_exe = str(env_path / ('python.exe' if sys.platform == 'win32' else 'bin/python')) # Original name
    if not Path(python_exe).exists():
        return None

    target_env_actual_python_version = get_environment_python_version(python_exe) # Get target env python version
    
    installed = get_installed_packages(python_exe) # Original name
    matching = []  # Original name
    missing = []   # Original name
    mismatched = []# Original name
    
    applicable_reqs_count = 0 # Renamed from original for clarity here
    for req in requirements: # Original name
        if not evaluate_marker(req.get('marker'), python_version, platform): # python_version here is script's for markers
            continue 
        applicable_reqs_count += 1

        pkg_name = normalize_name(req['name']) # Original name
        
        if pkg_name == 'python':
            if target_env_actual_python_version:
                if check_version_compatibility(target_env_actual_python_version, req['specs'], "python"):
                    matching.append("python") 
                else:
                    mismatched.append({
                        'name': "python",
                        'required': ','.join(f"{s['operator']}{s['version']}" for s in req['specs']),
                        'installed': target_env_actual_python_version, 
                        'original_req': req['original'] # Storing original_req for consistency
                    })
            else:
                missing.append(req) 
            continue 

        if pkg_name not in installed:
            missing.append(req)
            continue

        installed_pkg_version = installed[pkg_name] # Renamed from original for clarity
        if not check_version_compatibility(installed_pkg_version, req['specs'], pkg_name):
            mismatched.append({
                'name': pkg_name,
                'required': ','.join(f"{s['operator']}{s['version']}" for s in req['specs']),
                'installed': installed_pkg_version, # Use the renamed variable
                'original_req': req['original'] # Added for consistency
            })
            continue
        
        matching.append(pkg_name)

    # Original logic for total and compatibility score
    # Only count requirements that apply to this environment (this was already done by applicable_reqs_count)
    # applicable_reqs = [r for r in requirements if evaluate_marker(r.get('marker'), python_version, platform)]
    # total = len(applicable_reqs)
    total = applicable_reqs_count # Use the counter directly
    compatibility = (len(matching) / total * 100) if total > 0 else 100.0
    
    return {
        'env_name': Path(env_path).name or 'base', 
        'env_path': str(env_path),
        'compatibility': compatibility,
        'matching': matching,
        'missing': missing,
        'mismatched': mismatched,
        'total': total,
        'python_version_detected': target_env_actual_python_version # Store for display
    }

def infer_python_version_from_requirements(requirements): # Original name
    """
    Analyze requirements to determine the most likely compatible Python version.
    Returns a tuple of (major, minor) version numbers.
    """
    # Package-based Python version hints (original logic)
    package_version_hints = {
        'torch':      { '2.0.0': (3, 8), '2.1.0': (3, 8), '2.2.0': (3, 9), '2.7.0': (3, 9) },
        'pandas':     { '2.0.0': (3, 9), '2.1.0': (3, 9), '2.2.0': (3, 9) },
        'transformers':{ '4.30.0': (3, 8), '4.40.0': (3, 8), '4.45.0': (3, 9), '4.49.0': (3, 9) },
        'lightning':  { '2.0.0': (3, 8), '2.2.0': (3, 8), '2.5.0': (3, 9) },
        'datasets':   { '3.0.0': (3, 8), '3.3.0': (3, 9) },
    }
    
    direct_python_specs = [] # Original name
    
    for req in requirements: # Original name
        if req.get('name', '').lower() == 'python' and req.get('specs'): # Check for 'python' requirement
            for spec_detail_py_inf in req['specs']:
                try:
                    version_parts_py_inf = tuple(map(int, spec_detail_py_inf['version'].split('.')[:2]))
                    direct_python_specs.append((spec_detail_py_inf['operator'], version_parts_py_inf))
                except ValueError: 
                    continue 
        elif req.get('marker') and "python_version" in str(req.get('marker')): # Original marker check
            marker_str_inf = str(req.get('marker')) 
            matches_inf = re.findall(r"python_version\s*([<>=!~]+)\s*['\"]?([0-9]+\.[0-9]+(?:.[0-9]+)?)['\"]?", marker_str_inf)
            for op_marker_inf, ver_str_marker_inf in matches_inf:
                try:
                    version_parts_marker_inf = tuple(map(int, ver_str_marker_inf.split('.')[:2]))
                    direct_python_specs.append((op_marker_inf, version_parts_marker_inf))
                except ValueError:
                    continue

    if direct_python_specs: # Original logic for direct specs
        min_py_ver_val = (3, 6) 
        exact_py_ver_val = None
        for op_val_inf, ver_tuple_val_inf in direct_python_specs:
            if op_val_inf == '==':
                exact_py_ver_val = ver_tuple_val_inf 
                break
            if op_val_inf in ('>=', '>') and ver_tuple_val_inf > min_py_ver_val: 
                min_py_ver_val = ver_tuple_val_inf
        if exact_py_ver_val:
            return exact_py_ver_val
        return min_py_ver_val
    
    inferred_versions = [] # Original name
    for req_inf_pkg in requirements:
        pkg_name_lower_inf_val = req_inf_pkg['name'].lower()
        if pkg_name_lower_inf_val in package_version_hints:
            relevant_specs_inf_pkg = [s_inf_pkg for s_inf_pkg in req_inf_pkg['specs'] if s_inf_pkg['operator'] in ('>=', '==')]
            if relevant_specs_inf_pkg:
                for spec_detail_inf_pkg in relevant_specs_inf_pkg:
                    try:
                        req_pkg_version_parsed_inf_obj = parse_version(spec_detail_inf_pkg['version'])
                        for hint_pkg_ver_str_inf_val, py_ver_tuple_inf_val_pkg in sorted(
                                package_version_hints[pkg_name_lower_inf_val].items(),
                                key=lambda item_sort_inf_pkg: parse_version(item_sort_inf_pkg[0]), reverse=True):
                            hint_pkg_ver_parsed_inf_obj = parse_version(hint_pkg_ver_str_inf_val)
                            if spec_detail_inf_pkg['operator'] == '==' and req_pkg_version_parsed_inf_obj == hint_pkg_ver_parsed_inf_obj:
                                inferred_versions.append(py_ver_tuple_inf_val_pkg)
                                break 
                            elif spec_detail_inf_pkg['operator'] == '>=' and req_pkg_version_parsed_inf_obj >= hint_pkg_ver_parsed_inf_obj:
                                inferred_versions.append(py_ver_tuple_inf_val_pkg)
                                break 
                    except InvalidVersion:
                        continue 

    if inferred_versions:
        return sorted(inferred_versions, reverse=True)[0] 
    
    # Original PyTorch dev build check
    if any(req_dev_check['name'].lower() == 'torch' and any('dev' in s_dev_check['version'] for s_dev_check in req_dev_check['specs']) for req_dev_check in requirements):
        return (3, 9)
    
    return (3, 8) # Original fallback


def print_results(results, requirements_path, recommended_python_version, requirements): # Original parameter names
    """Display formatted compatibility results."""
    # 'requirements_path' now contains the dynamic install hint string from main()
    install_instruction_hint = requirements_path 

    print("\n" + "=" * 60)
    print(f"{bcolors.BOLD}ENVIRONMENT COMPATIBILITY RESULTS{bcolors.ENDC}")
    print("=" * 60)
    
    sorted_results = sorted(results, key=lambda x_sort_print: x_sort_print['compatibility'], reverse=True) 
    
    for result_print in sorted_results: 
        compat_score_val_print = result_print['compatibility']
        
        detected_py_ver_str_print = result_print.get('python_version_detected')
        env_name_display_print = result_print['env_name']
        if detected_py_ver_str_print and "Python" not in env_name_display_print : # Avoid double printing if already in name
            env_name_display_print += f" (Python {detected_py_ver_str_print})"

        if compat_score_val_print == 100: status_print = f"{bcolors.OKGREEN}COMPATIBLE{bcolors.ENDC}" 
        elif compat_score_val_print >= 80: status_print = f"{bcolors.WARNING}MOSTLY COMPATIBLE{bcolors.ENDC}"
        elif compat_score_val_print >= 50: status_print = f"{bcolors.WARNING}PARTIALLY COMPATIBLE{bcolors.ENDC}"
        else: status_print = f"{bcolors.FAIL}INCOMPATIBLE{bcolors.ENDC}"
            
        print(f"\n{bcolors.BOLD}Environment:{bcolors.ENDC} {env_name_display_print}")
        print(f"Status: {status_print} ({compat_score_val_print:.1f}% compatible)")
        print(f"Path: {result_print['env_path']}")
        print(f"Matching: {len(result_print['matching'])}/{result_print['total']} applicable packages")
        
        if result_print['missing']:
            print(f"\n{bcolors.BOLD}Missing packages:{bcolors.ENDC}")
            for pkg_missing_data_print in result_print['missing']:
                specs_str_val_print = ','.join(f"{s_data_print['operator']}{s_data_print['version']}" for s_data_print in pkg_missing_data_print['specs'])
                print(f"  - {pkg_missing_data_print['name']}{' (' + specs_str_val_print + ')' if specs_str_val_print else ''} (From: {pkg_missing_data_print['original']})")
        
        if result_print['mismatched']:
            print(f"\n{bcolors.BOLD}Version mismatches:{bcolors.ENDC}")
            for pkg_mismatch_data_print in result_print['mismatched']:
                print(f"  - {pkg_mismatch_data_print['name']}: required {pkg_mismatch_data_print['required']}, installed {pkg_mismatch_data_print['installed']} (From: {pkg_mismatch_data_print.get('original_req', pkg_mismatch_data_print.get('original', 'N/A'))})") # Use original_req or original

        if result_print['missing'] or result_print['mismatched']:
            print(f"\n{bcolors.BOLD}To fix in this environment:{bcolors.ENDC}")
            env_name_for_activate = result_print['env_name'].split(' (Python')[0].strip() # Get original name if version was appended
            if env_name_for_activate != 'current (this script)' and env_name_for_activate != 'current': # Handle both forms
                print(f"  conda activate \"{env_name_for_activate}\"") 
            print(f"  pip install {install_instruction_hint}") # Use the passed-in hint
            
        print("-" * 60)
    
    print("\n" + "=" * 60)
    print(f"{bcolors.BOLD}COMPATIBILITY OVERVIEW{bcolors.ENDC}")
    print("=" * 60)
    
    recommended_py_str_overview = f"{recommended_python_version[0]}.{recommended_python_version[1]}" 
    pip_install_cmd_overview_print = f"pip install {install_instruction_hint}" # Use the hint

    if not sorted_results:
        print(f"\n{bcolors.FAIL}No environments were analyzed or found.{bcolors.ENDC}") 
    else:
        print(f"\n{bcolors.BOLD}Top Compatible Environments:{bcolors.ENDC}")
        top_n_overview = min(3, len(sorted_results))
        for i_overview in range(top_n_overview):
            result_top_overview = sorted_results[i_overview]
            compat_score_top_overview = result_top_overview['compatibility']
            
            detected_py_ver_top_overview_str = result_top_overview.get('python_version_detected')
            env_name_top_overview_disp = result_top_overview['env_name']
            if detected_py_ver_top_overview_str and "Python" not in env_name_top_overview_disp:
                env_name_top_overview_disp += f" (Python {detected_py_ver_top_overview_str})"

            if compat_score_top_overview == 100: compat_str_overview_color = f"{bcolors.OKGREEN}{compat_score_top_overview:.1f}%{bcolors.ENDC}"
            elif compat_score_top_overview >= 50: compat_str_overview_color = f"{bcolors.WARNING}{compat_score_top_overview:.1f}%{bcolors.ENDC}"
            else: compat_str_overview_color = f"{bcolors.FAIL}{compat_score_top_overview:.1f}%{bcolors.ENDC}"
            print(f"{i_overview+1}. {env_name_top_overview_disp} - {compat_str_overview_color} - {len(result_top_overview['matching'])}/{result_top_overview['total']} packages")
        
        best_env_overview = sorted_results[0]
        best_env_name_orig_overview = best_env_overview['env_name'].split(' (Python')[0].strip()

        if best_env_overview['compatibility'] == 100:
            print(f"\n{bcolors.OKGREEN}✓ '{best_env_name_orig_overview}' is fully compatible!{bcolors.ENDC}")
        elif best_env_overview['compatibility'] >= 80:
            activate_cmd_overview_prefix = f"conda activate \"{best_env_name_orig_overview}\" && " if best_env_overview['env_name'] != 'current (this script)' and best_env_overview['env_name'] != 'current' else ''
            print(f"\n{bcolors.WARNING}⚠ '{best_env_name_orig_overview}' is mostly compatible ({best_env_overview['compatibility']:.1f}%).{bcolors.ENDC}")
            print(f"   Run: {activate_cmd_overview_prefix}{pip_install_cmd_overview_print}")
        else:
            print(f"\n{bcolors.FAIL}⚠ No highly compatible environments found.{bcolors.ENDC}")
            print(f"   Consider creating a new environment: conda create -n compatible-env python={recommended_py_str_overview} && conda activate compatible-env && {pip_install_cmd_overview_print}")

    if not results: # Original check
         print(f"\n{bcolors.FAIL}No compatible environments could be identified.{bcolors.ENDC}") 
         print(f"   Consider creating a new environment: conda create -n compatible-env python={recommended_py_str_overview} && conda activate compatible-env && {pip_install_cmd_overview_print}")

    pytorch_req_data_print = next((r_print_pyt for r_print_pyt in requirements if r_print_pyt['name'].lower() == 'torch'), None) 
    cuda_version_str_print_final = "unknown"
    if pytorch_req_data_print:
        for s_detail_pyt_print in pytorch_req_data_print.get('specs', []):
            if '+cu' in s_detail_pyt_print.get('version', ''):
                match_cuda_print = re.search(r'\+cu(\d+)', s_detail_pyt_print.get('version', ''))
                if match_cuda_print:
                    cuda_version_str_print_final = match_cuda_print.group(1)
                    if len(cuda_version_str_print_final) >= 3: 
                        cuda_version_str_print_final = f"{cuda_version_str_print_final[:-1]}.{cuda_version_str_print_final[-1]}"
    
    if cuda_version_str_print_final != "unknown":
        print(f"\n{bcolors.BOLD}Note:{bcolors.ENDC} Your requirements may involve PyTorch with CUDA {cuda_version_str_print_final}.")
        print(f"Make sure your system has compatible NVIDIA drivers installed.")
    
    print(f"\n{bcolors.BOLD}Recommended Python version (inferred from requirements):{bcolors.ENDC} {recommended_py_str_overview}")
    print("\n" + "=" * 60)

def main():
    print(f"{bcolors.HEADER}Environment Compatibility Checker{bcolors.ENDC}")
    print("=" * 60)
    
    script_python_version = f"{sys.version_info.major}.{sys.version_info.minor}" 
    script_platform = sys.platform 
    print(f"Script's Python version (for markers): {script_python_version} (Full: {sys.version.split()[0]})") 
    print(f"Script's platform: {script_platform}")
    
    try:
        import packaging
        print(f"Packaging library version: {packaging.__version__}")
    except ImportError:
        print(f"{bcolors.WARNING}Warning: 'packaging' module not found. Attempting to install it...{bcolors.ENDC}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "packaging"])
            print(f"{bcolors.OKGREEN}Successfully installed 'packaging'. Please re-run the script to use it.{bcolors.ENDC}")
            sys.exit(0) 
        except Exception as e_install_main_pkg:
            print(f"{bcolors.FAIL}Error installing 'packaging' module: {e_install_main_pkg}{bcolors.ENDC}")
            print("Version comparison and marker evaluation might be less accurate or fail.")
    
    if len(sys.argv) < 2:
        script_name_main_call = os.path.basename(__file__)
        print(f"{bcolors.FAIL}Error: Please provide a requirements file path OR a single requirement string.{bcolors.ENDC}")
        print(f"Usage (file): python {script_name_main_call} requirements.txt")
        print(f"Usage (single): python {script_name_main_call} \"package_name==version\"")
        sys.exit(1)

    cli_input_arg_main = sys.argv[1] 
    requirements_main_list = []      # Corresponds to 'requirements' in original main
    extra_urls_main_list = []        # Corresponds to 'extra_urls' in original main
    
    # This variable will store the string to be used for installation suggestions.
    # It will be passed as the 'requirements_path' argument to print_results.
    install_instruction_source = f"\"{cli_input_arg_main}\"" # Default for single string

    input_as_path_main_obj = Path(cli_input_arg_main)
    if input_as_path_main_obj.is_file(): 
        print(f"\nChecking requirements from file: {cli_input_arg_main}")
        try:
            requirements_main_list, extra_urls_main_list = parse_requirements_file(cli_input_arg_main) 
            install_instruction_source = f"-r \"{cli_input_arg_main}\"" # Update for file case
        except FileNotFoundError: 
             print(f"{bcolors.FAIL}Error: Requirements file not found at {cli_input_arg_main}{bcolors.ENDC}")
             sys.exit(1)
        except Exception as e_parse_file_main_exc: 
            print(f"{bcolors.FAIL}Error parsing requirements file '{cli_input_arg_main}': {e_parse_file_main_exc}{bcolors.ENDC}")
            sys.exit(1)
    else:
        print(f"\nChecking single requirement: \"{cli_input_arg_main}\"")
        try:
            requirements_main_list, extra_urls_main_list = parse_single_requirement_string(cli_input_arg_main)
            # install_instruction_source is already correctly set for single string
            if not requirements_main_list: 
                 raise InvalidRequirement("Input string parsed to empty list (e.g., comment or empty).")
        except InvalidRequirement as e_invalid_req_main_exc: 
            print(f"{bcolors.FAIL}Error: Input '{cli_input_arg_main}' is not a valid file AND could not be parsed as a requirement string: {e_invalid_req_main_exc}{bcolors.ENDC}")
            print(f"Examples: \"torch==2.0.0\", \"numpy>=1.20\", \"python==3.9\"")
            sys.exit(1)
        except Exception as e_parse_single_main_exc: 
            print(f"{bcolors.FAIL}Error processing single requirement input '{cli_input_arg_main}': {e_parse_single_main_exc}{bcolors.ENDC}")
            sys.exit(1)

    if not requirements_main_list: 
        print(f"{bcolors.FAIL}Error: No valid requirements were extracted from input: \"{cli_input_arg_main}\"{bcolors.ENDC}")
        sys.exit(1)
    
    recommended_python_version_tuple_main = infer_python_version_from_requirements(requirements_main_list) 
    recommended_python_str_main_disp = f"{recommended_python_version_tuple_main[0]}.{recommended_python_version_tuple_main[1]}" 
    
    print(f"\nFound {len(requirements_main_list)} requirement(s) to check.")
    print(f"Recommended Python version (inferred from requirements): {recommended_python_str_main_disp}")
    
    if extra_urls_main_list: 
        print("Extra index URLs found:") 
        for url_item_main_disp in extra_urls_main_list:
            print(f"  - {url_item_main_disp}")
    
    results_agg_main = [] # Corresponds to 'results' in original main
    
    current_script_env_path_resolved = Path(sys.prefix).resolve() 
    
    current_env_analysis_data_main = analyze_environment( 
        current_script_env_path_resolved, # Use resolved path
        requirements_main_list,
        script_python_version, 
        script_platform          
    )
    if current_env_analysis_data_main:
        current_env_analysis_data_main['env_name'] = 'current (this script)' # Original was 'current'
        results_agg_main.append(current_env_analysis_data_main)
    
    conda_exe_path_found_main = find_conda_executable() 
    if conda_exe_path_found_main:
        print(f"\nAttempting to check conda environments using {conda_exe_path_found_main}") 
        conda_environments_list_main = get_conda_envs(conda_exe_path_found_main)
        if not conda_environments_list_main:
            print(f"{bcolors.WARNING}No conda environments found or could not be listed.{bcolors.ENDC}")

        processed_conda_paths_main_set = {current_script_env_path_resolved}

        for conda_env_path_item_main in conda_environments_list_main: 
            resolved_conda_path_item_main = conda_env_path_item_main.resolve()
            if resolved_conda_path_item_main in processed_conda_paths_main_set:
                continue
            processed_conda_paths_main_set.add(resolved_conda_path_item_main)

            conda_env_result_item_main = analyze_environment( 
                resolved_conda_path_item_main, 
                requirements_main_list,
                script_python_version, 
                script_platform          
            )
            if conda_env_result_item_main:
                results_agg_main.append(conda_env_result_item_main)
    else:
        print(f"\n{bcolors.WARNING}Conda executable not found. Only the current Python environment was checked.{bcolors.ENDC}")
        print(f"If you use conda, ensure 'conda' is in your PATH or provide the path when prompted.")
    
    if results_agg_main: 
        # Pass install_instruction_source as the 'requirements_path' argument to print_results
        print_results(results_agg_main, install_instruction_source, recommended_python_version_tuple_main, requirements_main_list)
    else: 
        print(f"\n{bcolors.FAIL}No environments were analyzed, or analysis yielded no results.{bcolors.ENDC}")
        final_fallback_install_cmd_print = f"pip install {install_instruction_source}"
        print(f"Consider creating a new environment, e.g., with Python {recommended_python_str_main_disp}: conda create -n compatible-env python={recommended_python_str_main_disp} && conda activate compatible-env && {final_fallback_install_cmd_print}")

if __name__ == "__main__":
    main()
