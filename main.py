import numpy as np
import logging
import sys

class MolecularSimulation:
    def __init__(self,
                 number_atoms,
                 Lx,
                 maximum_steps,
                 dimensions=3,
                 Ly = None,
                 Lz = None,
                 desired_temperature=300,
                 time_step=1,
                 epsilon=0.1,
                 sigma=3,
                 atom_mass = 1,
                 displace_mc=0.5,
                 monte_carlo=False,
                 molecular_dynamics=False,
                 seed=None
                 ):
        
        self.number_atoms = number_atoms
        self.maximum_steps = maximum_steps
        self.Lx = Lx
        self.Ly = Ly
        self.Lz = Lz
        self.dimensions = dimensions
        self.time_step = time_step
        self.desired_temperature = desired_temperature
        self.epsilon = epsilon # kcal/mol
        self.sigma = sigma # Angstrom
        self.atom_mass = atom_mass
        self.displace_mc = displace_mc
        self.monte_carlo = monte_carlo
        self.molecular_dynamics = molecular_dynamics
        if seed is None:
            self.seed = np.random.randint(10000)
        else:
            self.seed = seed
        np.random.seed(self.seed)

        self.kB = 1.38e-23 # J/mol/K

        self.initialize_box()
        self.initialize_positions()

        a = self.calculate_potential_energy()
        print(a)

    def print_log(self):
        
        # Create and configure logger 
        logging.basicConfig(filename="log.txt", 
                            format='%(asctime)s %(message)s', 
                            filemode='w') 

        # Create a logger object 
        self.logger=logging.getLogger() 
        self.logger.setLevel(logging.DEBUG)
        self.logger.info("Initialization of the system") 
        self.logger.info("----------------------------") 
        self.logger.info("The initial number of atoms is " + str(self.number_atoms)) 
        if self.molecular_dynamics:
            self.logger.info("Initial velocity of CoM = " + str(np.round(self.velocity_com,3).tolist()) + " (NO UNIT SO FAR)") 
            self.logger.info("Initial kinetic energy = " + str(np.round(self.Ekin,3)) + " (NO UNIT SO FAR)") 
        self.logger.info("The system is of dimensions " + str(self.dimensions)) 
        self.logger.info("Box boundaries:") 
        self.logger.info("xlow = " + str(self.box_boundaries[0][0]) + " Å, xhigh = " + str(self.box_boundaries[0][1]) + " Å") 
        if self.dimensions>1:
            self.logger.info("ylow = " + str(self.box_boundaries[1][0]) + " Å, yhigh = " + str(self.box_boundaries[1][1]) + " Å") 
        if self.dimensions>2:
            self.logger.info("zlow = " + str(self.box_boundaries[2][0]) + " Å, zhigh = " + str(self.box_boundaries[2][1]) + " Å") 
        self.logger.info("*** Interaction parameters ***") 
        self.logger.info("epsilon = " + str(self.epsilon) + " Kcal/mol") 
        self.logger.info("sigma = " + str(self.sigma) + " Å")
        self.logger.info("atom mass = " + str(self.atom_mass) + " Å")
        self.logger.info("*** Monte Carlo parameters ***") 
        self.logger.info("displace_mc = " + str(self.displace_mc) + " Å")

    def initialize_box(self):
        """Define box boundaries based on Lx, Ly, and Lz.

        If Ly or Lz are None, then Lx is used instead"""
        box_boundaries = np.zeros((self.dimensions, 2))
        box_size = np.zeros(self.dimensions)
        box_boundaries[0] = -self.Lx/2, self.Lx/2
        box_size[0] = np.diff(box_boundaries[0])
        if self.dimensions > 1:
            if self.Ly is None:
                box_boundaries[1] = -self.Lx/2, self.Lx/2
            else:
                box_boundaries[1] = -self.Ly/2, self.Ly/2
            box_size[1] = np.diff(box_boundaries[1])
        if self.dimensions > 2:
            if self.Lz is None:
                box_boundaries[2] = -self.Lx/2, self.Lx/2
            else:
                box_boundaries[2] = -self.Lz/2, self.Lz/2
            box_size[2] = np.diff(box_boundaries[2])
        self.box_boundaries = box_boundaries
        self.box_size = box_size

    def initialize_positions(self):
        """Randomly pick positions and velocities."""

        atoms_positions = np.zeros((self.number_atoms, self.dimensions))
        for dim in np.arange(self.dimensions):
            atoms_positions[:, dim] = np.random.random(self.number_atoms)*np.diff(self.box_boundaries[dim]) - np.diff(self.box_boundaries[dim])/2
        self.atoms_positions = atoms_positions
        if self.molecular_dynamics:
            atoms_velocities = np.zeros((self.number_atoms, self.dimensions))
            for dim in np.arange(self.dimensions):  
                atoms_velocities[:, dim] = np.random.random(self.number_atoms)-0.5 # todo - must be rescalled
            self.atoms_velocities = atoms_velocities
            self.calculate_velocity_com()
            self.calculate_kinetic_energy()
            self.calculate_temperature()
            
            # to rescale temperature (attention units)
            # self.atoms_velocities = self.atoms_velocities*(self.desired_temperature/self.temperature)**0.5
            # self.calculate_temperature()

    def calculate_temperature(self):
        """Equation 4.2.2 in Frenkel-Smith 2002"""
        self.temperature = np.sum(self.atom_mass*np.linalg.norm(self.atoms_velocities, axis=1)**2)/self.number_atoms/self.kB

    def calculate_velocity_com(self):
        self.velocity_com = np.sum(self.atoms_velocities, axis=0)/self.number_atoms
    
    def calculate_kinetic_energy(self):
        kinetic_energy = 0
        for dim in np.arange(self.dimensions): 
            kinetic_energy += np.sum(self.atoms_velocities[:, dim]**2)
        self.Ekin = kinetic_energy/self.number_atoms

    def calculate_r(self, position_i):
        """Calculate the shortest distance between position_i and atoms_positions."""
        rij2 = np.zeros(self.number_atoms)
        rij = (np.remainder(position_i - self.atoms_positions + self.box_size/2., self.box_size) - self.box_size/2.).T
        for dim in np.arange(self.dimensions):
            rij2 += np.power(rij[dim, :], 2)
        return np.sqrt(rij2)

    def calculate_potential_energy(self):
        """Calculate potential energy assuming Lennard-Jones potential interaction.
        
        Output units are kcal/mol."""
        energy_potential = 0
        for position_i in self.atoms_positions:
            r = self.calculate_r(position_i)
            energy_potential_i = np.sum(4*self.epsilon*(np.power(self.sigma/r[r>0], 12)-np.power(self.sigma/r[r>0], 6)))
            energy_potential += energy_potential_i
        # Avoid counting potential energy twice
        energy_potential /= 2
        return energy_potential